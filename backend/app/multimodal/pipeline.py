"""
MultimodalPipeline: Dual text + multimodal document processing.

Flow:
  1. Parse document bytes via Docling → content_list
  2. separate_content()  → (text_content, modal_items)
  3. Text pipeline: engine.ainsert(text_content, file_paths=[file_path])
  4. Modal pipeline: for each modal item → select processor → await processor.process(...)
  5. Return ProcessingResult with counts
"""
from __future__ import annotations

import asyncio
import hashlib
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.multimodal.parser import parse_bytes, separate_content
from app.multimodal.processors import (
    EquationModalProcessor,
    ImageModalProcessor,
    TableModalProcessor,
)
from app.rag.engine import LightRAGEngine
from app.rag.utils import (
    TiktokenTokenizer,
    compute_mdhash_id,
    logger,
    openai_llm_func,
    openai_vision_func,
)


@dataclass
class ProcessingResult:
    """Summary of what was processed during document ingestion."""
    file_path: str
    text_length: int = 0
    text_chunk_count: int = 0
    modal_items_total: int = 0
    modal_items_processed: int = 0
    modal_items_failed: int = 0
    modal_type_counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    # First 4000 chars of Docling-extracted text — used by file_processor for summary
    extracted_text_snippet: str = ""

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


class MultimodalPipeline:
    """
    Orchestrates full document processing: text + images + tables + equations.

    Usage::

        pipeline = MultimodalPipeline()
        result = await pipeline.process_document(
            file_content=pdf_bytes,
            filename="lecture1.pdf",
            file_path="classrooms/7/lecture1.pdf",
            engine=rag_engine,
        )
    """

    def __init__(self, skip_modals: bool = False):
        """
        Args:
            skip_modals: If True, only process text (skip images/tables/equations).
                         Useful for testing or when Docling is unavailable.
        """
        self.skip_modals = skip_modals
        self._tokenizer = TiktokenTokenizer()

    async def process_document(
        self,
        file_content: bytes,
        filename: str,
        file_path: str,
        engine: LightRAGEngine,
        output_dir: str | None = None,
        phase: Literal["full", "phase1", "phase2"] = "full",
    ) -> ProcessingResult:
        """
        Full document processing pipeline.

        Args:
            file_content: Raw bytes of the document.
            filename:     Original filename (e.g. "lecture3.pdf").
            file_path:    Canonical path used for citation metadata in the KB
                          (e.g. the R2 object key or URL).
            engine:       Initialized LightRAGEngine for this classroom.
            output_dir:   Optional persistent directory for Docling artifacts.

        Returns:
            ProcessingResult with counts of what was processed.
        """
        result = ProcessingResult(file_path=file_path)
        _pipeline_t0 = time.time()
        logger.info(
            "MultimodalPipeline: START parsing '%s' (%d bytes)", filename, len(file_content)
        )

        # ── Temp directory management ─────────────────────────────────────────
        # We own the working directory so that Docling-extracted image files stay
        # on disk until AFTER modal processors have base64-encoded them for the
        # vision API.  Previously parse_bytes() cleaned up its own temp dir on
        # return, deleting images before ImageModalProcessor could read them.
        _managed_tmp: str | None = None
        _cleanup_tmp = output_dir is None
        if _cleanup_tmp:
            _managed_tmp = tempfile.mkdtemp(prefix="rag_pipeline_")
            output_dir = _managed_tmp

        try:
            # ── Step 1: Parse ────────────────────────────────────────────────
            try:
                loop = asyncio.get_event_loop()
                content_list = await loop.run_in_executor(
                    None, parse_bytes, file_content, filename, output_dir
                )
                logger.info(
                    "MultimodalPipeline: parse complete in %.2fs — %d content items for '%s'",
                    time.time() - _pipeline_t0, len(content_list), filename,
                )
            except Exception as e:
                logger.error(f"Document parse failed for '{filename}': {e}")
                result.errors.append(f"parse error: {e}")
                # Fallback: treat entire file as plain text
                try:
                    raw_text = file_content.decode("utf-8", errors="replace")
                    if raw_text.strip():
                        await engine.ainsert(raw_text, file_paths=[file_path],
                                             split_by_character="\n\n")
                        result.text_length = len(raw_text)
                except Exception as fallback_err:
                    result.errors.append(f"fallback text error: {fallback_err}")
                return result

            # ── Step 2: Separate text and modal items ────────────────────────
            text_content, modal_items = separate_content(content_list)
            result.text_length = len(text_content)
            result.modal_items_total = len(modal_items)
            result.extracted_text_snippet = text_content[:4000]

            for item in modal_items:
                t = item.get("type", "unknown")
                result.modal_type_counts[t] = result.modal_type_counts.get(t, 0) + 1

            modal_type_summary = ", ".join(
                f"{v} {k}" for k, v in result.modal_type_counts.items()
            ) or "none"
            logger.info(
                "MultimodalPipeline: '%s' separated — text=%d chars, modals=%d (%s)",
                filename, len(text_content), len(modal_items), modal_type_summary,
            )

            # ── Steps 3 + 4: Text and modal pipelines run concurrently ─────────
            # Text pipeline (chunk + embed + entity extraction + KG merge) and
            # modal pipeline (OCR pre-pass + vision API + per-modal entity extraction)
            # are independent after Docling parsing — start them together.
            #
            # Storage collision analysis (all safe):
            #   chunks_vdb  — different deterministic IDs, Chroma upsert idempotent
            #   text_chunks — different keys, asyncpg row-level locking
            #   entities_vdb / relationships_vdb / Neo4j — merge logic handles
            #     concurrent writes via read-modify-write + idempotent MERGE
            #
            # Temp directory (_managed_tmp) is cleaned up in the finally block
            # AFTER asyncio.gather returns, so image files stay valid for both
            # pipelines' full duration.

            async def _run_text_pipeline() -> None:
                if not text_content.strip():
                    return
                _text_t0 = time.time()
                logger.info(
                    "MultimodalPipeline: '%s' text pipeline start phase=%s (%d chars)",
                    filename, phase, len(text_content),
                )
                try:
                    await engine.ainsert(text_content, file_paths=[file_path],
                                         split_by_character="\n\n", phase=phase)
                    logger.info(
                        "MultimodalPipeline: '%s' text pipeline done in %.2fs",
                        filename, time.time() - _text_t0,
                    )
                except Exception as e:
                    logger.error(
                        "MultimodalPipeline: text insert failed for '%s' in %.2fs: %s",
                        filename, time.time() - _text_t0, e, exc_info=True,
                    )
                    result.errors.append(f"text insert error: {e}")

            if phase == "phase1":
                # Phase 1: chunk+embed text only — modal pipeline runs in Phase 2
                await _run_text_pipeline()
            else:
                # Phase 2 / full: entity extraction + modal pipeline run concurrently.
                # Image dedup runs here (outside the coroutine) so the deduplicated
                # list is available to _run_modal_pipeline's setup.

                # ── Modal pipeline coroutine (launched in gather below) ──────────
                # Image files in output_dir are still present — cleanup is in finally.

                # Deduplicate identical images by raw content hash before building
                # the modal pipeline. Done here (not inside the coroutine) so the
                # updated modal_items list is available to both pipelines' setup.
                _seen_img_hashes: set[str] = set()
                _deduped: list[dict] = []
                for _item in modal_items:
                    if _item.get("type") == "image":
                        _img_path = _item.get("img_path", "")
                        if _img_path:
                            try:
                                _h = hashlib.md5(Path(_img_path).read_bytes()).hexdigest()
                                if _h in _seen_img_hashes:
                                    logger.debug(
                                        "MultimodalPipeline: '%s' duplicate image skipped: %s",
                                        filename, _img_path,
                                    )
                                    result.modal_items_total -= 1
                                    continue
                                _seen_img_hashes.add(_h)
                            except Exception:
                                pass  # unreadable file — pass through to processor
                    _deduped.append(_item)
                modal_items = _deduped

            async def _run_modal_pipeline() -> None:
                if self.skip_modals or not modal_items:
                    return

                # OCR pre-pass: enrich image items with extracted text + text-only flag.
                # Runs concurrently in thread pool — no API rate limit applies to local OCR.
                # Results are stored in-place on each item dict and read by ImageModalProcessor:
                #   item["ocr_text"]    — text extracted from the image via EasyOCR
                #   item["is_text_only"] — True when the image is a scanned text page (no diagram)
                _image_items = [
                    _item for _item in modal_items
                    if _item.get("type") == "image" and _item.get("img_path")
                ]
                if _image_items:
                    _ocr_t0 = time.time()
                    await asyncio.gather(
                        *[_enrich_image_with_ocr(_item) for _item in _image_items],
                        return_exceptions=True,
                    )
                    _text_only_n = sum(1 for _item in _image_items if _item.get("is_text_only"))
                    logger.info(
                        "MultimodalPipeline: '%s' OCR pre-pass done in %.2fs — "
                        "%d text-only (vision skipped), %d with visuals",
                        filename, time.time() - _ocr_t0,
                        _text_only_n, len(_image_items) - _text_only_n,
                    )

                doc_id = compute_mdhash_id(text_content or filename, prefix="doc-")
                global_config = engine._make_global_config(background=True)

                shared = dict(
                    text_chunks_db=engine._text_chunks,
                    chunks_vdb=engine._chunks_vdb,
                    entities_vdb=engine._entities_vdb,
                    relationships_vdb=engine._relationships_vdb,
                    knowledge_graph_inst=engine._graph,
                    llm_model_func=openai_llm_func,
                    vision_model_func=openai_vision_func,
                    tokenizer=self._tokenizer,
                    global_config=global_config,
                    llm_response_cache=engine._llm_cache,
                    full_entities_storage=engine._full_entities,
                    full_relations_storage=engine._full_relations,
                )
                img_proc = ImageModalProcessor(**shared)
                tbl_proc = TableModalProcessor(**shared)
                eq_proc = EquationModalProcessor(**shared)

                for proc in (img_proc, tbl_proc, eq_proc):
                    proc.set_content_source(content_list)

                sem = asyncio.Semaphore(6)  # was 3 — allows 6 concurrent equation/image/table LLM calls

                async def _process_one(idx: int, item: dict) -> tuple[bool, str | None]:
                    async with sem:
                        itype = item.get("type", "unknown")
                        _modal_t0 = time.time()
                        try:
                            if itype == "image":
                                await img_proc.process(item, file_path, doc_id, chunk_order_index=idx)
                            elif itype == "table":
                                await tbl_proc.process(item, file_path, doc_id, chunk_order_index=idx)
                            elif itype == "equation":
                                await eq_proc.process(item, file_path, doc_id, chunk_order_index=idx)
                            else:
                                logger.debug(f"Skipping unknown modal type: {itype}")
                                return True, None
                            logger.debug(
                                "MultimodalPipeline: '%s' modal[%d] type=%s done in %.2fs",
                                filename, idx, itype, time.time() - _modal_t0,
                            )
                            return True, None
                        except Exception as e:
                            logger.warning(
                                "MultimodalPipeline: '%s' modal[%d] type=%s FAILED in %.2fs: %s",
                                filename, idx, itype, time.time() - _modal_t0, e,
                            )
                            return False, f"modal {itype}[{idx}]: {e}"

                tasks = [
                    asyncio.create_task(_process_one(idx, item))
                    for idx, item in enumerate(modal_items)
                ]
                outcomes = await asyncio.gather(*tasks, return_exceptions=True)

                for outcome in outcomes:
                    if isinstance(outcome, Exception):
                        result.modal_items_failed += 1
                        result.errors.append(str(outcome))
                    else:
                        success, err = outcome
                        if success:
                            result.modal_items_processed += 1
                        else:
                            result.modal_items_failed += 1
                            if err:
                                result.errors.append(err)

            if phase != "phase1":
                # Phase 2 / full: text entity extraction + modal pipeline concurrently.
                # They write to disjoint storage namespaces — no write conflicts.
                # See optimization-plan.md Fix 6 for the full collision analysis.
                # (Phase 1 already awaited _run_text_pipeline above.)
                await asyncio.gather(_run_text_pipeline(), _run_modal_pipeline())

            logger.info(
                "MultimodalPipeline: DONE '%s' in %.2fs — text=%d chars, "
                "modals=%d/%d processed, errors=%d",
                filename, time.time() - _pipeline_t0,
                result.text_length,
                result.modal_items_processed, result.modal_items_total,
                len(result.errors),
            )
            return result

        finally:
            # Clean up Docling working dir (images, input copy) only after all
            # modal processors have finished reading the image files.
            if _cleanup_tmp and _managed_tmp:
                shutil.rmtree(_managed_tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# EasyOCR singleton — lazy-initialized, thread-safe
# ---------------------------------------------------------------------------

_easyocr_reader: Any = None
_easyocr_lock = threading.Lock()


def _get_ocr_reader():
    """Return the shared EasyOCR reader, initializing it on first call."""
    global _easyocr_reader
    if _easyocr_reader is None:
        with _easyocr_lock:
            if _easyocr_reader is None:
                import easyocr
                logger.info("Initializing EasyOCR reader (first use — model weights loading)...")
                _easyocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
                logger.info("EasyOCR reader ready")
    return _easyocr_reader


def _run_ocr_sync(img_path: str) -> dict[str, Any]:
    """Blocking EasyOCR call. Runs in a thread pool executor — never call directly from async."""
    try:
        from PIL import Image as _PILImage
        reader = _get_ocr_reader()
        results = reader.readtext(img_path)
        text = " ".join(r[1] for r in results).strip()

        with _PILImage.open(img_path) as pil:
            img_area = (pil.width * pil.height) or 1

        bbox_area = sum(
            abs((r[0][2][0] - r[0][0][0]) * (r[0][2][1] - r[0][0][1]))
            for r in results
        )
        coverage = bbox_area / img_area

        return {
            "text": text,
            "is_text_only": len(text) > 300 and coverage > 0.5,
        }
    except Exception as e:
        logger.debug("OCR failed for %s: %s", img_path, e)
        return {"text": "", "is_text_only": False}


async def _enrich_image_with_ocr(item: dict) -> None:
    """Runs OCR on one image modal item and stores results in-place on the dict."""
    img_path = item.get("img_path", "")
    if not img_path:
        item["ocr_text"] = ""
        item["is_text_only"] = False
        return
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _run_ocr_sync, img_path)
    item["ocr_text"] = result["text"]
    item["is_text_only"] = result["is_text_only"]


# ---------------------------------------------------------------------------
# Module-level singleton for convenience
# ---------------------------------------------------------------------------

_default_pipeline: MultimodalPipeline | None = None


def get_pipeline(skip_modals: bool = False) -> MultimodalPipeline:
    """Return (or create) the module-level MultimodalPipeline singleton."""
    global _default_pipeline
    if _default_pipeline is None or _default_pipeline.skip_modals != skip_modals:
        _default_pipeline = MultimodalPipeline(skip_modals=skip_modals)
    return _default_pipeline
