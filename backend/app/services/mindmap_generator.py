"""
Mindmap generator — builds the hierarchical topic tree from a processed file.

Two LLM calls via `instructor`:
  1. RootTopic — determine the 2-5 word document topic and description.
  2. MindmapTreePayload — produce the full tree of sub-topics.

Both calls use the file-scoped graph context retrieved via engine.aquery
with only_need_context=True (skips the answer-generation step).
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import instructor
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.rag.base import QueryParam

logger = logging.getLogger("mindmap")

# ---------------------------------------------------------------------------
# Env-tunable constants
# ---------------------------------------------------------------------------

MAX_DEPTH = int(os.getenv("MINDMAP_MAX_DEPTH", "4"))
MAX_CHILDREN_PER_NODE = int(os.getenv("MINDMAP_MAX_CHILDREN_PER_NODE", "6"))
GENERATION_MODEL = os.getenv("MINDMAP_GENERATION_MODEL", "gpt-4o-mini")

# RAG retrieval settings for tree generation
_GEN_CHUNK_TOP_K = 25
_GEN_TOP_K = 30
_GEN_TRAVERSAL_HOPS = 2
_GEN_MAX_NEIGHBORS = 40

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class MindmapTooShallowError(Exception):
    pass


class FilePreconditionError(Exception):
    pass


# ---------------------------------------------------------------------------
# Instructor client (lazy singleton)
# ---------------------------------------------------------------------------

_instructor_client: instructor.AsyncInstructor | None = None


def _get_instructor_client() -> instructor.AsyncInstructor:
    global _instructor_client
    if _instructor_client is None:
        _instructor_client = instructor.from_openai(AsyncOpenAI())
    return _instructor_client


# ---------------------------------------------------------------------------
# Pydantic models for structured LLM output
# ---------------------------------------------------------------------------


class RootTopic(BaseModel):
    topic: str = Field(
        min_length=2,
        max_length=120,
        description="2–5 word well-defined topic (not the filename)",
    )
    description: str = Field(
        min_length=20,
        max_length=400,
        description="1–2 sentence description of the document's central thesis",
    )


class MindmapNode(BaseModel):
    topic: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=20, max_length=400)
    children: list["MindmapNode"] = Field(default_factory=list, max_length=6)


# Must be called after the class body so the self-referencing forward ref
# is resolved before instructor introspects the JSON schema.
MindmapNode.model_rebuild()


class MindmapTreePayload(BaseModel):
    children: list[MindmapNode] = Field(min_length=2, max_length=8)


# ---------------------------------------------------------------------------
# Tree assembly
# ---------------------------------------------------------------------------


def _count_nodes(node: dict) -> int:
    """Recursively count all nodes including the given one."""
    return 1 + sum(_count_nodes(c) for c in node.get("children", []))


def assemble_tree(root: RootTopic, payload: MindmapTreePayload) -> dict:
    """Convert instructor output to the stable tree_data JSONB shape."""
    counter = itertools.count(1)

    def assign_ids(node: MindmapNode, depth: int) -> dict:
        nid = f"n_{next(counter):04d}"
        return {
            "id": nid,
            "topic": node.topic.strip(),
            "description": node.description.strip(),
            "depth": depth,
            "children": [assign_ids(c, depth + 1) for c in node.children],
        }

    return {
        "version": 1,
        "root": {
            "id": "n_root",
            "topic": root.topic.strip(),
            "description": root.description.strip(),
            "depth": 0,
            "children": [assign_ids(c, 1) for c in payload.children],
        },
    }


# ---------------------------------------------------------------------------
# Main generation entry point
# ---------------------------------------------------------------------------


async def build_mindmap_tree(engine: Any, file: Any) -> tuple[dict, dict]:
    """
    Build the hierarchical mindmap tree for a file.

    Returns (tree_data dict, generation_meta dict).
    Raises MindmapTooShallowError if the tree has fewer than 2 children.
    """
    client = _get_instructor_client()
    t0 = time.monotonic()
    tokens_in = tokens_out = 0

    # ── Step 1: Pull file-scoped graph context ────────────────────────────
    context_query = (
        "List the document's main topic, the major sub-topics it covers, and the "
        "relationships between them. Include named entities, key concepts, and concrete "
        "examples. Be exhaustive — this is the source material for a hierarchical mindmap."
    )

    context_result = await asyncio.wait_for(
        engine.aquery(
            context_query,
            QueryParam(
                mode="mix",
                only_need_context=True,
                chunk_top_k=_GEN_CHUNK_TOP_K,
                top_k=_GEN_TOP_K,
                traversal_hops=_GEN_TRAVERSAL_HOPS,
                max_graph_neighbors=_GEN_MAX_NEIGHBORS,
                file_filter=file.file_url,
            ),
        ),
        timeout=90.0,
    )

    raw_context = ""
    if context_result:
        raw_context = getattr(context_result, "content", "") or ""
    if not raw_context.strip():
        raise FilePreconditionError(
            "No content retrieved for this file. Ensure the file is fully processed."
        )

    # ── Step 2: Determine root topic ──────────────────────────────────────
    root_system = (
        "You name documents by their core topic. Return a 2–5 word topic that captures "
        "the document's central subject — not the literal filename, not a chapter heading. "
        "Then a 1–2 sentence description.\n\n"
        "Example:\n"
        "  filename: \"Chapter1_HRM_With_Cartoons_Icons_and_Video.pptx\"\n"
        "  topic: \"Human Resource Management\"\n"
        "  description: \"Foundational practices for managing people in organisations, "
        "covering recruitment, training, and performance evaluation.\""
    )
    root_prompt = f"FILENAME: {file.filename}\n\nDOCUMENT CONTEXT:\n{raw_context[:6000]}"

    root_resp = await asyncio.wait_for(
        client.chat.completions.create(
            model=GENERATION_MODEL,
            messages=[
                {"role": "system", "content": root_system},
                {"role": "user", "content": root_prompt},
            ],
            response_model=RootTopic,
            temperature=0.2,
        ),
        timeout=60.0,
    )
    root: RootTopic = root_resp  # type: ignore[assignment]
    if hasattr(root_resp, "_raw_response"):
        usage = getattr(root_resp._raw_response, "usage", None)
        if usage:
            tokens_in += getattr(usage, "prompt_tokens", 0)
            tokens_out += getattr(usage, "completion_tokens", 0)

    # ── Step 3: Generate hierarchical tree ───────────────────────────────
    tree_system = (
        f"You build hierarchical mindmaps from study material. "
        f"Output a tree of topics with the central topic \"{root.topic}\" as the implicit root.\n\n"
        f"Constraints:\n"
        f"- Root has 2-8 direct children (top-level branches).\n"
        f"- Each non-leaf has 2-{MAX_CHILDREN_PER_NODE} children.\n"
        f"- Maximum tree depth is {MAX_DEPTH} levels below the root.\n"
        f"- Each topic is a 2-5 word noun phrase, no verbs, no questions.\n"
        f"- Each description is 1-2 sentences, drawn strictly from the document.\n"
        f"- Do NOT invent topics absent from the document.\n"
        f"- Prefer breadth at level 1 (major sub-topics) and depth at deeper levels.\n"
        f"- Skip a level rather than padding with redundant siblings.\n\n"
        f"Output JSON only."
    )

    tree_resp = await asyncio.wait_for(
        client.chat.completions.create(
            model=GENERATION_MODEL,
            messages=[
                {"role": "system", "content": tree_system},
                {"role": "user", "content": f"DOCUMENT CONTEXT:\n{raw_context[:18000]}"},
            ],
            response_model=MindmapTreePayload,
            temperature=0.3,
            max_retries=2,
        ),
        timeout=90.0,
    )
    payload: MindmapTreePayload = tree_resp  # type: ignore[assignment]
    if hasattr(tree_resp, "_raw_response"):
        usage = getattr(tree_resp._raw_response, "usage", None)
        if usage:
            tokens_in += getattr(usage, "prompt_tokens", 0)
            tokens_out += getattr(usage, "completion_tokens", 0)

    if len(payload.children) < 2:
        raise MindmapTooShallowError(
            "Document too short for a useful mindmap — fewer than 2 top-level topics found."
        )

    tree = assemble_tree(root, payload)
    elapsed = time.monotonic() - t0

    meta = {
        "model": GENERATION_MODEL,
        "traversal_hops": _GEN_TRAVERSAL_HOPS,
        "max_neighbors": _GEN_MAX_NEIGHBORS,
        "elapsed_s": round(elapsed, 2),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "context_chars": len(raw_context),
    }

    node_count = _count_nodes(tree["root"])
    logger.info(
        "mindmap generated",
        extra={
            "file_id": file.id,
            "node_count": node_count,
            "root_topic": root.topic,
            "elapsed_s": meta["elapsed_s"],
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        },
    )

    return tree, meta
