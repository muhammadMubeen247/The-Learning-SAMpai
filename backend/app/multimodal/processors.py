"""
Modal processors for images, tables, and equations.
Adapted from RAG-Anything/raganything/modalprocessors.py for the FYP storage stack.

Each processor:
  1. Receives a modal content dict (from Docling)
  2. Generates an enhanced text description via LLM/vision API
  3. Stores the description as a text chunk in KV + vector DBs
  4. Upserts an entity node into the knowledge graph
  5. Runs entity extraction on the description chunk to build relations

The processors talk directly to our storage objects rather than going through
a LightRAG instance.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from app.rag.base import BaseGraphStorage, BaseKVStorage, BaseVectorStorage
from app.rag.operate import extract_entities, merge_nodes_and_edges
from app.rag.prompt import PROMPTS
from app.rag.utils import (
    TiktokenTokenizer,
    compute_mdhash_id,
    logger,
    openai_vision_func,
)


# ---------------------------------------------------------------------------
# Robust JSON parser (ported from RAG-Anything BaseModalProcessor)
# ---------------------------------------------------------------------------

def _extract_json_candidates(text: str) -> list[str]:
    """Extract all plausible JSON objects from a raw LLM response."""
    # Strip <think> / <thinking> tags first
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL | re.IGNORECASE)

    candidates: list[str] = []

    # Fenced code blocks
    for block in re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL):
        candidates.append(block)

    # Balanced braces
    brace_depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if brace_depth == 0:
                start = i
            brace_depth += 1
        elif ch == "}":
            brace_depth -= 1
            if brace_depth == 0 and start != -1:
                candidates.append(text[start : i + 1])

    # Greedy fallback
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        candidates.append(m.group(0))

    return candidates


def _fix_smart_quotes(s: str) -> str:
    return (
        s.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201e", '"')
    )


def robust_json_parse(response: str) -> dict:
    """Multi-strategy JSON recovery for LLM modal analysis responses."""
    for raw in _extract_json_candidates(response):
        # Strategy 1: direct parse
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # Strategy 2: fix smart quotes + trailing commas
        try:
            cleaned = _fix_smart_quotes(raw)
            cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    # Strategy 3: regex field extraction
    desc = re.search(r'"detailed_description"\s*:\s*"((?:[^"\\]|\\.)*)"', response, re.DOTALL)
    name = re.search(r'"entity_name"\s*:\s*"((?:[^"\\]|\\.)*)"', response)
    etype = re.search(r'"entity_type"\s*:\s*"((?:[^"\\]|\\.)*)"', response)
    summary = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"', response, re.DOTALL)
    description_text = desc.group(1) if desc else ""
    return {
        "detailed_description": description_text,
        "entity_info": {
            "entity_name": name.group(1) if name else "unknown_entity",
            "entity_type": etype.group(1) if etype else "unknown",
            "summary": summary.group(1) if summary else description_text[:100],
        },
    }


# ---------------------------------------------------------------------------
# Base processor
# ---------------------------------------------------------------------------

class BaseModalProcessor:
    """
    Base class for image, table, and equation processors.

    Constructor receives storage objects directly instead of a LightRAG instance.
    """

    def __init__(
        self,
        text_chunks_db: BaseKVStorage,
        chunks_vdb: BaseVectorStorage,
        entities_vdb: BaseVectorStorage,
        relationships_vdb: BaseVectorStorage,
        knowledge_graph_inst: BaseGraphStorage,
        llm_model_func,
        vision_model_func,
        tokenizer: TiktokenTokenizer,
        global_config: dict,
        llm_response_cache: BaseKVStorage | None = None,
        full_entities_storage: BaseKVStorage | None = None,
        full_relations_storage: BaseKVStorage | None = None,
    ):
        self.text_chunks_db = text_chunks_db
        self.chunks_vdb = chunks_vdb
        self.entities_vdb = entities_vdb
        self.relationships_vdb = relationships_vdb
        self.knowledge_graph_inst = knowledge_graph_inst
        self.llm_model_func = llm_model_func
        self.vision_model_func = vision_model_func
        self.tokenizer = tokenizer
        self.global_config = global_config
        self.llm_response_cache = llm_response_cache
        self.full_entities_storage = full_entities_storage
        self.full_relations_storage = full_relations_storage

        # Content source for context extraction (set per-document)
        self.content_source: list | None = None

    def set_content_source(self, content_list: list) -> None:
        """Provide the full parsed content list for context windowing."""
        self.content_source = content_list

    async def _get_modal_cache(self, cache_key: str) -> str | None:
        """Return cached LLM/vision response for this modal item, or None."""
        if self.llm_response_cache is None:
            return None
        record = await self.llm_response_cache.get_by_id(f"modal_{cache_key}")
        return record.get("response") if isinstance(record, dict) else None

    async def _set_modal_cache(self, cache_key: str, response: str) -> None:
        """Persist LLM/vision response for this modal item."""
        if self.llm_response_cache is None:
            return
        await self.llm_response_cache.upsert({f"modal_{cache_key}": {"response": response}})

    def _get_surrounding_text(self, item: dict, window: int = 2, max_tokens: int = 3000) -> str:
        """Return surrounding text context for a modal item, with token truncation.

        window=2 covers 2 slides before and after in index mode — important for
        PPTX where each slide has sparse text (bullet points only).
        max_tokens=3000 gives GPT-4o richer context for image/table descriptions.

        Falls back to index-based proximity when Docling does not populate page_idx
        (which sets all items to page 0, making page-based windowing useless).
        """
        if not self.content_source:
            return ""

        # Detect whether page_idx is meaningful: if all blocks share the same value,
        # Docling didn't populate it — use index-based proximity instead.
        all_page_idxs = [b.get("page_idx", 0) for b in self.content_source]
        use_index_mode = len(set(all_page_idxs)) <= 1

        if use_index_mode:
            # Find item by identity (same object reference — guaranteed by separate_content)
            try:
                item_pos = next(i for i, b in enumerate(self.content_source) if b is item)
            except StopIteration:
                return ""
            lo = max(0, item_pos - window * 3)
            hi = min(len(self.content_source), item_pos + window * 3 + 1)
            blocks = self.content_source[lo:hi]
        else:
            page = item.get("page_idx", 0)
            blocks = [b for b in self.content_source if abs(b.get("page_idx", 0) - page) <= window]

        parts = [
            b.get("text", "").strip()
            for b in blocks
            if b.get("type") == "text" and b.get("text", "").strip()
        ]
        joined = "\n".join(parts)

        # Token-aware truncation
        tokens = self.tokenizer.encode(joined)
        if len(tokens) > max_tokens:
            joined = self.tokenizer.decode(tokens[:max_tokens])

        return joined

    async def _create_entity_and_chunk(
        self,
        modal_chunk: str,
        entity_info: dict,
        file_path: str,
        doc_id: str,
        chunk_order_index: int = 0,
    ) -> list[str]:
        """Store the description as a chunk and entity, then run entity extraction.

        Returns the list of entity names extracted from the modal description chunk.
        Used to build belongs_to edges back to the modal root entity.
        """
        chunk_id = compute_mdhash_id(modal_chunk, prefix="chunk-")
        tokens = len(self.tokenizer.encode(modal_chunk))

        chunk_data = {
            "tokens": tokens,
            "content": modal_chunk,
            "chunk_order_index": chunk_order_index,
            "full_doc_id": doc_id,
            "file_path": file_path,
        }
        # KV store
        await self.text_chunks_db.upsert({chunk_id: chunk_data})

        # Vector store (chunks)
        await self.chunks_vdb.upsert(
            {chunk_id: {"content": modal_chunk, "full_doc_id": doc_id, "file_path": file_path}}
        )

        # Graph node
        entity_name = entity_info["entity_name"]
        entity_type = entity_info.get("entity_type", "image")
        summary = entity_info.get("summary", "")

        node_data = {
            "entity_id": entity_name,
            "entity_type": entity_type,
            "description": summary,
            "source_id": chunk_id,
            "file_path": file_path,
            "created_at": int(time.time()),
        }
        await self.knowledge_graph_inst.upsert_node(entity_name, node_data)

        # Entity VDB
        entity_vdb_id = compute_mdhash_id(entity_name, prefix="ent-")
        await self.entities_vdb.upsert(
            {
                entity_vdb_id: {
                    "entity_name": entity_name,
                    "entity_type": entity_type,
                    "content": f"{entity_name}\n{summary}",
                    "source_id": chunk_id,
                    "file_path": file_path,
                }
            }
        )

        # Entity/relation extraction from modal description chunk
        extracted_entity_names: list[str] = []
        try:
            chunk_results = await extract_entities(
                {chunk_id: chunk_data},
                self.global_config,
                llm_response_cache=self.llm_response_cache,
            )
            if chunk_results:
                extracted_entity_names = await merge_nodes_and_edges(
                    chunk_results=chunk_results,
                    knowledge_graph_inst=self.knowledge_graph_inst,
                    entity_vdb=self.entities_vdb,
                    relationships_vdb=self.relationships_vdb,
                    global_config=self.global_config,
                    llm_response_cache=self.llm_response_cache,
                    full_entities_storage=self.full_entities_storage,
                    full_relations_storage=self.full_relations_storage,
                    doc_id=doc_id,
                    file_path=file_path,
                )
        except Exception as e:
            logger.warning(f"Entity extraction on modal chunk failed: {e}")

        # belongs_to edges: each extracted text entity → modal root entity
        # This connects visual/tabular content to its related concepts in the KG
        for ext_name in extracted_entity_names:
            if ext_name and ext_name != entity_name:
                try:
                    await self.knowledge_graph_inst.upsert_edge(
                        ext_name,
                        entity_name,
                        {
                            "keywords": "belongs to, appears in",
                            "description": f"{ext_name} appears in {entity_name}",
                            "weight": "1.0",
                            "source_id": chunk_id,
                            "file_path": file_path,
                            "created_at": str(int(time.time())),
                        },
                    )
                except Exception as e:
                    logger.debug(f"belongs_to edge skipped {ext_name}→{entity_name}: {e}")

        return extracted_entity_names


# ---------------------------------------------------------------------------
# Image processor
# ---------------------------------------------------------------------------

class ImageModalProcessor(BaseModalProcessor):
    """Processor for image modal items from Docling output."""

    def _encode_image(self, image_path: str) -> str:
        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to encode image {image_path}: {e}")
            return ""

    def _media_type(self, image_path: str) -> str:
        ext = Path(image_path).suffix.lower().lstrip(".")
        return {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "webp": "image/webp",
        }.get(ext, "image/jpeg")

    async def process(
        self,
        item: dict,
        file_path: str,
        doc_id: str,
        chunk_order_index: int = 0,
    ) -> None:
        """Analyze image and insert into knowledge graph."""
        image_path = item.get("img_path", "")
        captions = item.get("image_caption", "")
        footnotes = item.get("image_footnote", "")
        # Populated by the OCR pre-pass in pipeline.py before this processor runs
        ocr_text: str = item.get("ocr_text", "")
        is_text_only: bool = item.get("is_text_only", False)

        if not image_path or not Path(image_path).exists():
            logger.warning(f"Image not found, skipping: {image_path}")
            return

        entity_name = f"image_{compute_mdhash_id(image_path)[:8]}"

        # Text-only scan (e.g. CamScanner page): store OCR text directly, skip vision API.
        if is_text_only and ocr_text:
            logger.info(
                "ImageModalProcessor: text-only scan detected, skipping vision API: %s",
                image_path,
            )
            entity_info = {
                "entity_name": entity_name,
                "entity_type": "document_scan",
                "summary": ocr_text[:200],
            }
            modal_chunk = f"[Scanned document page]\nPath: {image_path}\n\n{ocr_text}"
            await self._create_entity_and_chunk(
                modal_chunk, entity_info, file_path, doc_id, chunk_order_index
            )
            return

        # Build vision prompt context: merge page-proximity surrounding text with
        # any OCR text extracted directly from this image (labels, captions, equations).
        surrounding = self._get_surrounding_text(item)
        context_parts = []
        if surrounding:
            context_parts.append(surrounding)
        if ocr_text:
            context_parts.append(f"Text visible within this image (OCR extracted):\n{ocr_text}")
        context = "\n\n".join(context_parts)

        if context:
            prompt = PROMPTS["vision_prompt_with_context"].format(
                context=context,
                entity_name=entity_name,
                image_path=image_path,
                captions=captions or "None",
                footnotes=footnotes or "None",
            )
        else:
            prompt = PROMPTS["vision_prompt"].format(
                entity_name=entity_name,
                image_path=image_path,
                captions=captions or "None",
                footnotes=footnotes or "None",
            )

        image_b64 = self._encode_image(image_path)
        if not image_b64:
            return

        cache_key = hashlib.md5(image_b64.encode()).hexdigest()

        try:
            cached = await self._get_modal_cache(cache_key)
            if cached:
                response = cached
            else:
                response = await self.vision_model_func(
                    prompt,
                    image_data=image_b64,
                    system_prompt=PROMPTS["IMAGE_ANALYSIS_SYSTEM"],
                    image_media_type=self._media_type(image_path),
                )
                await self._set_modal_cache(cache_key, response)
            parsed = robust_json_parse(response)
            description = parsed.get("detailed_description", response[:500])
            entity_info_raw = parsed.get("entity_info", {})
            entity_info = {
                "entity_name": entity_info_raw.get("entity_name", entity_name),
                "entity_type": "image",
                "summary": entity_info_raw.get("summary", description[:200]),
            }
        except Exception as e:
            logger.error(f"Vision model error for {image_path}: {e}")
            description = f"Image at {image_path}"
            entity_info = {"entity_name": entity_name, "entity_type": "image", "summary": description}

        modal_chunk = PROMPTS["image_chunk"].format(
            image_path=image_path,
            captions=captions or "None",
            footnotes=footnotes or "None",
            enhanced_caption=description,
        )
        await self._create_entity_and_chunk(
            modal_chunk, entity_info, file_path, doc_id, chunk_order_index
        )


# ---------------------------------------------------------------------------
# Table processor
# ---------------------------------------------------------------------------

class TableModalProcessor(BaseModalProcessor):
    """Processor for table modal items from Docling output."""

    async def process(
        self,
        item: dict,
        file_path: str,
        doc_id: str,
        chunk_order_index: int = 0,
    ) -> None:
        """Analyze table and insert into knowledge graph."""
        table_body = item.get("table_body", [])
        caption = item.get("table_caption", "")
        footnote = item.get("table_footnote", "")
        img_path = item.get("img_path", "")

        entity_name = f"table_{compute_mdhash_id(str(table_body or caption))[:8]}"
        cache_key = hashlib.md5(
            (str(table_body) + str(caption) + str(footnote)).encode()
        ).hexdigest()
        context = self._get_surrounding_text(item)

        if context:
            prompt = PROMPTS["table_prompt_with_context"].format(
                context=context,
                entity_name=entity_name,
                table_img_path=img_path or "N/A",
                table_caption=caption or "N/A",
                table_body=json.dumps(table_body, ensure_ascii=False)[:2000] if table_body else "N/A",
                table_footnote=footnote or "N/A",
            )
        else:
            prompt = PROMPTS["table_prompt"].format(
                entity_name=entity_name,
                table_img_path=img_path or "N/A",
                table_caption=caption or "N/A",
                table_body=json.dumps(table_body, ensure_ascii=False)[:2000] if table_body else "N/A",
                table_footnote=footnote or "N/A",
            )

        try:
            cached = await self._get_modal_cache(cache_key)
            if cached:
                response = cached
            else:
                response = await self.llm_model_func(
                    prompt,
                    system_prompt=PROMPTS["TABLE_ANALYSIS_SYSTEM"],
                )
                await self._set_modal_cache(cache_key, response)
            parsed = robust_json_parse(response)
            description = parsed.get("detailed_description", response[:500])
            entity_info_raw = parsed.get("entity_info", {})
            entity_info = {
                "entity_name": entity_info_raw.get("entity_name", entity_name),
                "entity_type": "table",
                "summary": entity_info_raw.get("summary", description[:200]),
            }
        except Exception as e:
            logger.error(f"Table analysis error: {e}")
            description = f"Table: {caption or str(table_body)[:100]}"
            entity_info = {"entity_name": entity_name, "entity_type": "table", "summary": description}

        modal_chunk = PROMPTS["table_chunk"].format(
            table_img_path=img_path or "N/A",
            table_caption=caption or "N/A",
            table_body=json.dumps(table_body, ensure_ascii=False)[:1000] if table_body else "N/A",
            table_footnote=footnote or "N/A",
            enhanced_caption=description,
        )
        await self._create_entity_and_chunk(
            modal_chunk, entity_info, file_path, doc_id, chunk_order_index
        )


# ---------------------------------------------------------------------------
# Equation processor
# ---------------------------------------------------------------------------

class EquationModalProcessor(BaseModalProcessor):
    """Processor for mathematical equation modal items from Docling output."""

    async def process(
        self,
        item: dict,
        file_path: str,
        doc_id: str,
        chunk_order_index: int = 0,
    ) -> None:
        """Analyze equation and insert into knowledge graph."""
        equation_text = item.get("text", "")
        equation_format = item.get("text_format", "latex")

        if not equation_text.strip():
            return

        entity_name = f"equation_{compute_mdhash_id(equation_text)[:8]}"
        cache_key = hashlib.md5((equation_text + equation_format).encode()).hexdigest()
        context = self._get_surrounding_text(item)

        if context:
            prompt = PROMPTS["equation_prompt_with_context"].format(
                context=context,
                entity_name=entity_name,
                equation_text=equation_text,
                equation_format=equation_format,
            )
        else:
            prompt = PROMPTS["equation_prompt"].format(
                entity_name=entity_name,
                equation_text=equation_text,
                equation_format=equation_format,
            )

        try:
            cached = await self._get_modal_cache(cache_key)
            if cached:
                response = cached
            else:
                response = await self.llm_model_func(
                    prompt,
                    system_prompt=PROMPTS["EQUATION_ANALYSIS_SYSTEM"],
                )
                await self._set_modal_cache(cache_key, response)
            parsed = robust_json_parse(response)
            description = parsed.get("detailed_description", response[:500])
            entity_info_raw = parsed.get("entity_info", {})
            entity_info = {
                "entity_name": entity_info_raw.get("entity_name", entity_name),
                "entity_type": "equation",
                "summary": entity_info_raw.get("summary", description[:200]),
            }
        except Exception as e:
            logger.error(f"Equation analysis error: {e}")
            description = f"Mathematical equation: {equation_text}"
            entity_info = {"entity_name": entity_name, "entity_type": "equation", "summary": description}

        modal_chunk = PROMPTS["equation_chunk"].format(
            equation_text=equation_text,
            equation_format=equation_format,
            enhanced_caption=description,
        )
        await self._create_entity_and_chunk(
            modal_chunk, entity_info, file_path, doc_id, chunk_order_index
        )
