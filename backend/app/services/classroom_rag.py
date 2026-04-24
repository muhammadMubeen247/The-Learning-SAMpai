"""
ClassroomRAGService: per-classroom LightRAGEngine lifecycle manager.

Engines are process-lifetime singletons — created lazily on first access,
cached by classroom_id, and shut down gracefully on app stop.
"""
from __future__ import annotations

import asyncio
import logging

from app.rag.engine import LightRAGEngine

logger = logging.getLogger(__name__)

_lock = asyncio.Lock()


class ClassroomRAGService:
    """
    Manages one LightRAGEngine per classroom.

    Usage::

        engine = await classroom_rag_service.get_engine(classroom_id=7)
        result = await engine.aquery("What is gradient descent?", param)
    """

    def __init__(self) -> None:
        self._engines: dict[int, LightRAGEngine] = {}

    async def get_engine(self, classroom_id: int) -> LightRAGEngine:
        """
        Return (or create + initialize) the engine for a classroom.

        Thread-safe: uses an asyncio lock so concurrent first-access calls
        don't create duplicate engines.
        """
        if classroom_id in self._engines:
            return self._engines[classroom_id]

        async with _lock:
            # Double-check after acquiring the lock
            if classroom_id in self._engines:
                return self._engines[classroom_id]

            workspace = f"classroom_{classroom_id}"
            logger.info(f"Creating LightRAGEngine for workspace '{workspace}'")

            engine = LightRAGEngine(workspace=workspace)
            await engine.initialize()

            self._engines[classroom_id] = engine
            logger.info(f"LightRAGEngine ready for classroom {classroom_id}")
            return engine

    async def finalize_all(self) -> None:
        """
        Gracefully shut down all engines (flush pending writes, close pools).
        Call this from the FastAPI lifespan shutdown handler.
        """
        if not self._engines:
            return

        logger.info(f"Finalizing {len(self._engines)} RAG engine(s)...")
        await asyncio.gather(
            *(engine.finalize() for engine in self._engines.values()),
            return_exceptions=True,
        )
        self._engines.clear()
        logger.info("All RAG engines finalized.")


# Module-level singleton
classroom_rag_service = ClassroomRAGService()
