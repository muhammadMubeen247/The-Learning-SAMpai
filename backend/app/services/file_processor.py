"""
File Processing Service
Orchestrates background processing pipeline for uploaded files.

Pipeline:
  1. Set status → PROCESSING
  2. Get classroom engine (LightRAGEngine)
  3. Process document via MultimodalPipeline (text + images/tables/equations)
  4. Generate a brief summary via LLM (stored in files.description)
  5. Set status → COMPLETED
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
    """Handles the complete file processing pipeline using LightRAG + multimodal."""

    async def process_file(
        self,
        file_id: int,
        file_content: bytes,
        filename: str,
    ) -> bool:
        async with AsyncSessionLocal() as db:
            try:
                result = await db.execute(select(File).where(File.id == file_id))
                file = result.scalar_one_or_none()
                if not file:
                    logger.error(f"[file_processor] File {file_id} not found in DB")
                    return False

                logger.info(
                    "[file_processor] START file_id=%d filename='%s' content_size=%d bytes",
                    file_id, filename, len(file_content),
                )
                _proc_t0 = time.time()

                file.processing_status = ProcessingStatus.PROCESSING
                await db.commit()
                logger.info(f"[file_processor] Status→PROCESSING file_id={file_id}")

                result = await db.execute(select(Folder).where(Folder.id == file.folder_id))
                folder = result.scalar_one_or_none()
                if not folder:
                    raise ValueError(f"Folder {file.folder_id} not found")
                classroom_id = folder.classroom_id

                engine = await classroom_rag_service.get_engine(classroom_id)
                logger.info(f"[file_processor] RAG engine ready for classroom_id={classroom_id}")

                logger.info("[file_processor] citation key (file_url)='%s'", file.file_url)
                pipeline = get_pipeline(skip_modals=False)
                result_doc = await asyncio.wait_for(
                    pipeline.process_document(
                        file_content=file_content,
                        filename=filename,
                        file_path=file.file_url,
                        engine=engine,
                    ),
                    timeout=600,
                )

                if result_doc.errors:
                    for err in result_doc.errors:
                        logger.warning(f"[file_processor] Pipeline warning file_id={file_id}: {err}")

                logger.info(
                    f"[file_processor] Pipeline complete file_id={file_id}: "
                    f"text={result_doc.text_length}chars "
                    f"modals={result_doc.modal_items_processed}/{result_doc.modal_items_total}"
                )

                logger.info(f"[file_processor] Generating summary file_id={file_id}...")
                summary = f"Document: {filename}"
                text_snippet = result_doc.extracted_text_snippet or ""

                if not text_snippet and file.file_type in ("txt",):
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
                        logger.info(
                            f"[file_processor] Summary generated file_id={file_id} len={len(summary)}"
                        )
                    except Exception as summary_err:
                        logger.warning(
                            f"[file_processor] Summary generation failed file_id={file_id}: {summary_err}"
                        )
                else:
                    logger.warning(
                        f"[file_processor] No text extracted for summary file_id={file_id}, "
                        f"using filename fallback"
                    )

                file.description = summary
                file.processing_status = ProcessingStatus.COMPLETED
                file.processed_at = datetime.utcnow()
                await db.commit()

                logger.info(
                    "[file_processor] Status→COMPLETED file_id=%d in %.2fs processed_at=%s",
                    file_id, time.time() - _proc_t0, file.processed_at,
                )
                return True

            except asyncio.TimeoutError:
                logger.error(
                    f"[file_processor] TIMEOUT file_id={file_id} — processing exceeded 600s, marking FAILED"
                )
                try:
                    result = await db.execute(select(File).where(File.id == file_id))
                    f = result.scalar_one_or_none()
                    if f:
                        f.processing_status = ProcessingStatus.FAILED
                        await db.commit()
                except Exception:
                    pass
                return False

            except Exception as e:
                logger.error(f"[file_processor] FAILED file_id={file_id}: {e}", exc_info=True)
                try:
                    result = await db.execute(select(File).where(File.id == file_id))
                    f = result.scalar_one_or_none()
                    if f:
                        f.processing_status = ProcessingStatus.FAILED
                        await db.commit()
                except Exception as update_err:
                    logger.error(
                        f"[file_processor] Could not mark FAILED status file_id={file_id}: {update_err}"
                    )
                return False


file_processor = FileProcessor()
