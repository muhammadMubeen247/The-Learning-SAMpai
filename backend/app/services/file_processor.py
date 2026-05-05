"""
File Processing Service
Orchestrates the two-phase background processing pipeline for uploaded files.

Phase 1 (~15–30 s): Docling parse + chunk + embed → chunks_vdb ready
  → status = NAIVE_READY  → chat, flashcards, @SAMpai become usable

Phase 2 (~150–300 s, background): entity extraction + KG merge + modal processing
  → status = COMPLETED    → quiz, mindmap become usable
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from sqlalchemy import select

from app.database.session import AsyncSessionLocal
from app.models.file import File, ProcessingStatus
from app.models.folder import Folder
from app.multimodal.pipeline import get_pipeline
from app.services.classroom_rag import classroom_rag_service

logger = logging.getLogger(__name__)


class FileProcessor:
    """Handles the split file processing pipeline using LightRAG + multimodal."""

    async def process_file(
        self,
        file_id: int,
        file_content: bytes,
        filename: str,
    ) -> bool:
        """
        Phase 1 entry point — called as a FastAPI BackgroundTask on upload.
        Runs chunking + embedding only, then flips to NAIVE_READY and queues Phase 2.
        """
        async with AsyncSessionLocal() as db:
            try:
                result = await db.execute(select(File).where(File.id == file_id))
                file = result.scalar_one_or_none()
                if not file:
                    logger.error("[file_processor] File %d not found in DB", file_id)
                    return False

                logger.info(
                    "[file_processor] Phase 1 START file_id=%d filename='%s' size=%d bytes",
                    file_id, filename, len(file_content),
                )
                _t0 = time.time()

                file.processing_status = ProcessingStatus.PROCESSING
                await db.commit()

                result = await db.execute(select(Folder).where(Folder.id == file.folder_id))
                folder = result.scalar_one_or_none()
                if not folder:
                    raise ValueError(f"Folder {file.folder_id} not found")
                classroom_id = folder.classroom_id

                engine = await classroom_rag_service.get_engine(classroom_id)
                pipeline = get_pipeline(skip_modals=False)

                # Phase 1: parse + chunk + embed text only.
                # Runs with a tighter timeout — should complete in < 60 s.
                result_doc = await asyncio.wait_for(
                    pipeline.process_document(
                        file_content=file_content,
                        filename=filename,
                        file_path=file.file_url,
                        engine=engine,
                        phase="phase1",
                    ),
                    timeout=120,
                )

                if result_doc.errors:
                    for err in result_doc.errors:
                        logger.warning(
                            "[file_processor] Phase 1 warning file_id=%d: %s", file_id, err
                        )

                # Generate the 2–3 sentence summary now (1 cheap LLM call) so the
                # file card displays a description as soon as the file is usable.
                summary = await self._generate_summary(
                    file_id, filename, file_content, result_doc, file.file_type
                )
                file.description = summary

                file.processing_status = ProcessingStatus.NAIVE_READY
                await db.commit()

                logger.info(
                    "[file_processor] Phase 1 DONE file_id=%d in %.2fs → NAIVE_READY",
                    file_id, time.time() - _t0,
                )

                # Phase 2 runs fully in the background — it does NOT block the caller.
                # We deliberately do NOT await it here.
                asyncio.create_task(
                    self._process_phase2(
                        file_id=file_id,
                        file_content=file_content,
                        filename=filename,
                        file_url=file.file_url,
                        classroom_id=classroom_id,
                    )
                )
                return True

            except asyncio.TimeoutError:
                logger.error(
                    "[file_processor] Phase 1 TIMEOUT file_id=%d — exceeded 120s", file_id
                )
                await self._mark_failed(file_id)
                return False

            except Exception as e:
                logger.error(
                    "[file_processor] Phase 1 FAILED file_id=%d: %s", file_id, e, exc_info=True
                )
                await self._mark_failed(file_id)
                return False

    async def _process_phase2(
        self,
        file_id: int,
        file_content: bytes,
        filename: str,
        file_url: str,
        classroom_id: int,
    ) -> None:
        """
        Phase 2 background task — entity extraction + KG merge + modal processing.
        Sets COMPLETED when done; sets FAILED if it errors (chat stays usable at NAIVE_READY).
        """
        async with AsyncSessionLocal() as db:
            try:
                _t0 = time.time()
                logger.info(
                    "[file_processor] Phase 2 START file_id=%d classroom_id=%d",
                    file_id, classroom_id,
                )

                engine = await classroom_rag_service.get_engine(classroom_id)
                pipeline = get_pipeline(skip_modals=False)

                result_doc = await asyncio.wait_for(
                    pipeline.process_document(
                        file_content=file_content,
                        filename=filename,
                        file_path=file_url,
                        engine=engine,
                        phase="phase2",
                    ),
                    timeout=600,
                )

                if result_doc.errors:
                    for err in result_doc.errors:
                        logger.warning(
                            "[file_processor] Phase 2 warning file_id=%d: %s", file_id, err
                        )

                result = await db.execute(select(File).where(File.id == file_id))
                file = result.scalar_one_or_none()
                if file:
                    file.processing_status = ProcessingStatus.COMPLETED
                    file.processed_at = datetime.utcnow()
                    await db.commit()

                logger.info(
                    "[file_processor] Phase 2 DONE file_id=%d in %.2fs → COMPLETED",
                    file_id, time.time() - _t0,
                )

            except asyncio.TimeoutError:
                logger.error(
                    "[file_processor] Phase 2 TIMEOUT file_id=%d — exceeded 600s", file_id
                )
                await self._mark_failed(file_id)

            except Exception as e:
                logger.error(
                    "[file_processor] Phase 2 FAILED file_id=%d: %s", file_id, e, exc_info=True
                )
                await self._mark_failed(file_id)

    async def _generate_summary(
        self, file_id: int, filename: str, file_content: bytes, result_doc, file_type: str | None
    ) -> str:
        """Generate a 2–3 sentence document summary for the file card."""
        summary = f"Document: {filename}"
        text_snippet = result_doc.extracted_text_snippet or ""

        if not text_snippet and file_type in ("txt",):
            try:
                text_snippet = file_content.decode("utf-8", errors="replace")[:4000]
            except Exception:
                pass

        if text_snippet.strip():
            try:
                from app.rag.utils import openai_llm_func
                summary = await openai_llm_func(
                    prompt=(
                        f"In 2-3 sentences, summarize what this document is about:\n\n{text_snippet}"
                    ),
                    system_prompt=(
                        "You are a concise academic assistant. Give a brief, factual summary "
                        "of the document's main topic, key concepts, and scope."
                    ),
                )
            except Exception as summary_err:
                logger.warning(
                    "[file_processor] Summary generation failed file_id=%d: %s",
                    file_id, summary_err,
                )
        return summary

    async def _mark_failed(self, file_id: int) -> None:
        """Set processing_status to FAILED, best-effort."""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(File).where(File.id == file_id))
                f = result.scalar_one_or_none()
                if f:
                    f.processing_status = ProcessingStatus.FAILED
                    await db.commit()
        except Exception as err:
            logger.error(
                "[file_processor] Could not mark FAILED for file_id=%d: %s", file_id, err
            )


    async def resume_phase2(self, file_id: int) -> bool:
        """
        Re-queue Phase 2 for a NAIVE_READY file that lost its background task
        (e.g., after a server restart).  Downloads bytes from R2 then calls
        _process_phase2 directly — Phase 1 chunks already in ChromaDB are NOT
        re-inserted.
        Returns True if the task was queued, False if the file state prevents it.
        """
        import asyncio as _asyncio
        import os

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(File).where(File.id == file_id))
            file = result.scalar_one_or_none()
            if not file:
                logger.warning("[file_processor] resume_phase2: file_id=%d not found", file_id)
                return False

            if file.processing_status not in (
                ProcessingStatus.NAIVE_READY,
                ProcessingStatus.PROCESSING,
            ):
                logger.info(
                    "[file_processor] resume_phase2: skipping file_id=%d status=%s",
                    file_id, file.processing_status.value,
                )
                return False

            result2 = await db.execute(select(Folder).where(Folder.id == file.folder_id))
            folder = result2.scalar_one_or_none()
            if not folder:
                logger.error("[file_processor] resume_phase2: folder not found for file_id=%d", file_id)
                return False

            classroom_id = folder.classroom_id
            file_key = file.file_key
            file_url = file.file_url
            filename = file.filename

        # Download from R2 (sync boto3 → thread)
        try:
            from app.lib.r2 import s3
            file_content: bytes = await _asyncio.to_thread(
                lambda: s3.get_object(
                    Bucket=os.getenv("R2_BUCKET_NAME"), Key=file_key
                )["Body"].read()
            )
        except Exception as e:
            logger.error(
                "[file_processor] resume_phase2: R2 download failed file_id=%d: %s", file_id, e
            )
            return False

        logger.info(
            "[file_processor] resume_phase2: queuing Phase 2 for file_id=%d classroom_id=%d",
            file_id, classroom_id,
        )
        _asyncio.create_task(
            self._process_phase2(
                file_id=file_id,
                file_content=file_content,
                filename=filename,
                file_url=file_url,
                classroom_id=classroom_id,
            )
        )
        return True


file_processor = FileProcessor()
