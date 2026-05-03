"""
Per-node chat service for mindmaps.

Responsibilities
  - explore_node: check if a node has been explored; if not, write a MARKER
    row and a PENDING placeholder ASSISTANT row, then fire a background task
    to generate the real summary.
  - generate_node_summary_task: BackgroundTask that fetches context via the
    RAG engine and updates the placeholder row.
  - ask_in_thread: conversational follow-up scoped to the current file, with
    the active node injected as context.
  - _build_history: assemble conversation history (last N messages + anchor).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import AsyncSessionLocal
from app.models.file import File
from app.models.mindmap import Mindmap, MindmapNodeChat, MindmapMessageRole
from app.rag.base import QueryParam
from app.rag.utils import openai_llm_func
from app.schemas.mindmap import ExploreNodeResponse
from app.services.classroom_rag import classroom_rag_service
from app.services.mindmap_service import _find_node

logger = logging.getLogger("mindmap.chat")

# RAG params for node-summary generation
_SUMMARY_CHUNK_TOP_K = 15
_SUMMARY_TOP_K = 20
_SUMMARY_TRAVERSAL_HOPS = 2
_SUMMARY_MAX_NEIGHBORS = 30

# RAG params for conversational follow-up
_ASK_CHUNK_TOP_K = 10
_ASK_TOP_K = 15
_ASK_TRAVERSAL_HOPS = 1
_ASK_MAX_NEIGHBORS = 20

# Per-(user, mindmap) concurrency lock so we don't generate two node
# summaries at the same time for the same user.
_summary_locks: dict[tuple[int, int], asyncio.Semaphore] = {}
_locks_mutex = asyncio.Lock()


async def _get_lock(mindmap_id: int, user_id: int) -> asyncio.Semaphore:
    key = (mindmap_id, user_id)
    async with _locks_mutex:
        if key not in _summary_locks:
            _summary_locks[key] = asyncio.Semaphore(1)
        return _summary_locks[key]


# ---------------------------------------------------------------------------
# Explore node
# ---------------------------------------------------------------------------


async def explore_node(
    db: AsyncSession,
    mindmap_id: int,
    node_id: str,
    user_id: int,
) -> ExploreNodeResponse:
    """
    If the node has already been explored by this user, return the last
    assistant message id.  Otherwise, insert a MARKER + pending ASSISTANT
    placeholder and return their ids.
    """
    # Check for existing non-marker assistant message for this node
    result = await db.execute(
        select(MindmapNodeChat)
        .where(
            MindmapNodeChat.mindmap_id == mindmap_id,
            MindmapNodeChat.user_id == user_id,
            MindmapNodeChat.node_id == node_id,
            MindmapNodeChat.role == MindmapMessageRole.ASSISTANT,
            MindmapNodeChat.message_metadata["pending"].as_string() != "true",
        )
        .order_by(MindmapNodeChat.created_at.desc())
        .limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return ExploreNodeResponse(
            already_explored=True,
            last_message_id=existing.id,
        )

    # Insert MARKER
    marker = MindmapNodeChat(
        mindmap_id=mindmap_id,
        user_id=user_id,
        node_id=node_id,
        role=MindmapMessageRole.MARKER,
        content="",
        message_metadata={"node_id": node_id},
    )
    db.add(marker)
    await db.flush()

    # Insert pending ASSISTANT placeholder
    placeholder = MindmapNodeChat(
        mindmap_id=mindmap_id,
        user_id=user_id,
        node_id=node_id,
        role=MindmapMessageRole.ASSISTANT,
        content="",
        message_metadata={"pending": True, "node_id": node_id},
    )
    db.add(placeholder)
    await db.flush()

    return ExploreNodeResponse(
        already_explored=False,
        marker_id=marker.id,
        placeholder_id=placeholder.id,
    )


# ---------------------------------------------------------------------------
# Background task: generate node summary
# ---------------------------------------------------------------------------


def _build_summary_question(
    node: dict,
    root_topic: str,
    filename: str,
) -> str:
    """Build the RAG query for a node-level summary."""
    return (
        f"In the context of \"{root_topic}\" (from \"{filename}\"), "
        f"explain the sub-topic \"{node['topic']}\" in detail. "
        f"{node.get('description', '')} "
        f"Include key concepts, relevant examples, definitions, and relationships "
        f"to neighbouring topics."
    )


async def generate_node_summary_task(
    mindmap_id: int,
    node_id: str,
    placeholder_id: int,
    file_id: int,
    classroom_id: int,
    user_id: int,
) -> None:
    """
    BackgroundTask: generate a summary for a specific mindmap node and write
    it into the placeholder row.
    """
    sem = await _get_lock(mindmap_id, user_id)
    async with sem:
        async with AsyncSessionLocal() as db:
            try:
                # Load dependencies
                mindmap = await db.get(Mindmap, mindmap_id)
                file = await db.get(File, file_id)
                if mindmap is None or file is None:
                    raise ValueError("mindmap or file not found")

                node = _find_node(mindmap.tree_data or {}, node_id)
                if node is None:
                    raise ValueError(f"node {node_id} not found in tree")

                engine = await classroom_rag_service.get_engine(classroom_id)
                question = _build_summary_question(
                    node,
                    mindmap.root_topic or "the document",
                    file.filename,
                )

                t0 = time.monotonic()
                result = await asyncio.wait_for(
                    engine.aquery(
                        question,
                        QueryParam(
                            mode="mix",
                            chunk_top_k=_SUMMARY_CHUNK_TOP_K,
                            top_k=_SUMMARY_TOP_K,
                            traversal_hops=_SUMMARY_TRAVERSAL_HOPS,
                            max_graph_neighbors=_SUMMARY_MAX_NEIGHBORS,
                            file_filter=file.file_url,
                        ),
                    ),
                    timeout=90.0,
                )
                elapsed = round(time.monotonic() - t0, 2)

                answer = getattr(result, "content", None) or ""

                placeholder = await db.get(MindmapNodeChat, placeholder_id)
                if placeholder:
                    placeholder.content = answer
                    placeholder.message_metadata = {
                        "node_id": node_id,
                        "elapsed_s": elapsed,
                    }
                    await db.commit()

            except Exception as exc:
                logger.exception(
                    "node summary failed mindmap_id=%s node_id=%s", mindmap_id, node_id
                )
                placeholder = await db.get(MindmapNodeChat, placeholder_id)
                if placeholder:
                    placeholder.content = (
                        "Sorry, I couldn't generate a summary for this topic. "
                        "Please try again."
                    )
                    placeholder.message_metadata = {
                        "node_id": node_id,
                        "error": str(exc)[:200],
                    }
                    await db.commit()


# ---------------------------------------------------------------------------
# Conversational ask
# ---------------------------------------------------------------------------


async def _build_history(
    db: AsyncSession,
    mindmap_id: int,
    user_id: int,
    active_node_id: Optional[str],
    limit: int = 10,
) -> list[dict[str, str]]:
    """
    Assemble conversation history for the LLM:
      - last `limit` non-MARKER messages for this user+mindmap
      - anchor: the most recent completed ASSISTANT message for the active node
    """
    result = await db.execute(
        select(MindmapNodeChat)
        .where(
            MindmapNodeChat.mindmap_id == mindmap_id,
            MindmapNodeChat.user_id == user_id,
            MindmapNodeChat.role != MindmapMessageRole.MARKER,
        )
        .order_by(MindmapNodeChat.created_at.desc())
        .limit(limit)
    )
    msgs = list(reversed(result.scalars().all()))

    history = []

    # Optional anchor: the node summary acts as the first assistant turn
    if active_node_id:
        anchor_result = await db.execute(
            select(MindmapNodeChat)
            .where(
                MindmapNodeChat.mindmap_id == mindmap_id,
                MindmapNodeChat.user_id == user_id,
                MindmapNodeChat.node_id == active_node_id,
                MindmapNodeChat.role == MindmapMessageRole.ASSISTANT,
                MindmapNodeChat.message_metadata["pending"].as_string() != "true",
            )
            .order_by(MindmapNodeChat.created_at.desc())
            .limit(1)
        )
        anchor = anchor_result.scalar_one_or_none()
        if anchor and anchor.content:
            history.append({"role": "assistant", "content": anchor.content[:2000]})

    for msg in msgs:
        if msg.role == MindmapMessageRole.USER:
            history.append({"role": "user", "content": msg.content})
        elif msg.role == MindmapMessageRole.ASSISTANT and msg.content:
            history.append({"role": "assistant", "content": msg.content})

    return history


async def ask_in_thread(
    db: AsyncSession,
    mindmap_id: int,
    user_id: int,
    content: str,
    active_node_id: Optional[str],
    file_id: int,
    classroom_id: int,
) -> MindmapNodeChat:
    """
    Persist the user's question, call the RAG engine for an answer, persist
    the assistant's response, and return the assistant message.
    """
    # Load mindmap + file for context
    mindmap = await db.get(Mindmap, mindmap_id)
    file = await db.get(File, file_id)
    if mindmap is None or file is None:
        raise ValueError("mindmap or file not found")

    # Resolve active node label
    active_label = None
    if active_node_id and mindmap.tree_data:
        node = _find_node(mindmap.tree_data, active_node_id)
        active_label = node["topic"] if node else None

    # Augment user query with active node context
    augmented = content
    if active_label:
        augmented = f"[Currently exploring: {active_label}]\n\n{content}"

    # Persist user message
    user_msg = MindmapNodeChat(
        mindmap_id=mindmap_id,
        user_id=user_id,
        node_id=active_node_id,
        role=MindmapMessageRole.USER,
        content=content,
        message_metadata={"active_node_id": active_node_id},
    )
    db.add(user_msg)
    await db.flush()

    # Build conversation history
    history = await _build_history(db, mindmap_id, user_id, active_node_id, limit=10)

    try:
        engine = await classroom_rag_service.get_engine(classroom_id)
        t0 = time.monotonic()
        result = await asyncio.wait_for(
            engine.aquery(
                augmented,
                QueryParam(
                    mode="mix",
                    chunk_top_k=_ASK_CHUNK_TOP_K,
                    top_k=_ASK_TOP_K,
                    traversal_hops=_ASK_TRAVERSAL_HOPS,
                    max_graph_neighbors=_ASK_MAX_NEIGHBORS,
                    conversation_history=history,
                    history_turns=len(history),
                    file_filter=file.file_url,
                ),
            ),
            timeout=60.0,
        )
        elapsed = round(time.monotonic() - t0, 2)
        answer = getattr(result, "content", None) or "I couldn't find an answer in the document."
        meta: dict = {"elapsed_s": elapsed, "active_node_id": active_node_id}
    except Exception as exc:
        logger.exception("ask_in_thread failed mindmap_id=%s", mindmap_id)
        answer = "Sorry, I encountered an error while searching the document. Please try again."
        meta = {"error": str(exc)[:200]}

    # Persist assistant message
    assistant_msg = MindmapNodeChat(
        mindmap_id=mindmap_id,
        user_id=user_id,
        node_id=active_node_id,
        role=MindmapMessageRole.ASSISTANT,
        content=answer,
        message_metadata=meta,
    )
    db.add(assistant_msg)
    await db.commit()

    return assistant_msg
