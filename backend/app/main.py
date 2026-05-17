import os
import logging

# NumPy 2.x compatibility shim — must run before chromadb is imported
import numpy as np
if not hasattr(np, "float_"):
    np.float_ = np.float64   # type: ignore[attr-defined]
if not hasattr(np, "int_"):
    np.int_ = np.intp        # type: ignore[attr-defined]

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(
    dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
    override=True,
)


def _configure_logging() -> None:
    """
    Re-apply our log format after uvicorn's startup dictConfig has run.
    uvicorn calls dictConfig with disable_existing_loggers=True which silences
    every logger created at import time (all our route/service loggers).
    We fix this by:
      1. Setting a single StreamHandler on the root logger
      2. Re-enabling every logger that dictConfig disabled
      3. Setting propagate=True on all uvicorn sub-loggers so they use our format
    """
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler()
    handler.setFormatter(fmt)

    root = logging.getLogger()
    _log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    root.setLevel(getattr(logging, _log_level_name, logging.INFO))
    root.handlers = [handler]

    # Re-enable every logger that uvicorn's dictConfig silenced
    for logger_obj in logging.root.manager.loggerDict.values():
        if isinstance(logger_obj, logging.Logger):
            logger_obj.disabled = False
            logger_obj.propagate = True   # let root handler carry everything
            logger_obj.handlers = []      # no duplicate output

    # Ensure uvicorn access log is visible at INFO
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.INFO)
        lg.disabled = False
        lg.propagate = True
        lg.handlers = []

    # chromadb 0.4.24 emits a single ClientStartEvent via posthog 7.x before
    # its Settings(anonymized_telemetry=False) has been applied. The call
    # fails with "capture() takes 1 positional argument but 3 were given"
    # and is logged at ERROR. Post-init events are correctly silenced by
    # our Settings, so this one line is cosmetic noise. Keep CRITICAL so
    # future real issues from that logger still surface.
    logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

from app.database.init_db import init_db
from app.routes import auth, classroom, folder, file, chat, quiz, flashcards as flashcards_router
from app.routes import group_chat as group_chat_router
from app.routes import mindmap as mindmap_router
from app.routes import announcements as announcements_router


async def _load_sampai_user_id(app: FastAPI) -> None:
    from sqlalchemy import select, text
    from app.database.session import AsyncSessionLocal
    from app.models.user import User

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User.id).where(User.username == "SAMpai", User.is_system.is_(True))
        )
        sampai_id = result.scalar_one_or_none()

    if sampai_id is None:
        raise RuntimeError(
            "SAMpai system user not found. Run 'alembic upgrade head' to seed it."
        )
    app.state.sampai_user_id = sampai_id
    logging.getLogger(__name__).info(f"SAMpai system user cached: id={sampai_id}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────
    # Apply our log format AFTER uvicorn's dictConfig has run
    _configure_logging()
    logging.getLogger(__name__).info("Learning SAMpai backend starting up")
    await init_db()
    await _load_sampai_user_id(app)

    # Real-time WebSocket connection manager + optional Redis fan-out
    from app.realtime.connection_manager import ConnectionManager
    from app.realtime.redis_client import init_redis, close_redis

    cm = ConnectionManager()
    redis = None
    if os.getenv("WS_FANOUT", "memory") == "redis":
        redis = await init_redis()
    await cm.start(redis)
    app.state.connection_manager = cm
    app.state.redis = redis

    # Group chat AI agent
    from app.services.group_chat_agent import GroupChatAgent
    from app.services.classroom_rag import classroom_rag_service
    import httpx
    from openai import AsyncOpenAI

    openai_client = AsyncOpenAI(
        http_client=httpx.AsyncClient(
            timeout=httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=5.0),
        ),
    )
    agent = GroupChatAgent(
        sampai_user_id=app.state.sampai_user_id,
        classroom_rag_service=classroom_rag_service,
        connection_manager=cm,
        openai_client=openai_client,
    )
    app.state.group_chat_agent = agent

    # ── Phase 2 recovery ─────────────────────────────────────────────────
    # Any file left in NAIVE_READY or PROCESSING at startup lost its Phase 2
    # background task to a server restart.  Re-queue them now so they can
    # reach COMPLETED without the user having to re-upload.
    async def _recover_phase2() -> None:
        from sqlalchemy import select as _select
        from app.database.session import AsyncSessionLocal as _Session
        from app.models.file import File as _File, ProcessingStatus as _PS
        from app.services.file_processor import file_processor as _fp

        async with _Session() as db:
            rows = await db.execute(
                _select(_File.id).where(
                    _File.processing_status.in_([_PS.NAIVE_READY, _PS.PROCESSING])
                )
            )
            ids = [r[0] for r in rows.all()]

        if ids:
            logging.getLogger(__name__).info(
                "Phase 2 recovery: found %d file(s) needing Phase 2 → %s", len(ids), ids
            )
            for fid in ids:
                try:
                    await _fp.resume_phase2(fid)
                except Exception as _e:
                    logging.getLogger(__name__).error(
                        "Phase 2 recovery failed for file_id=%d: %s", fid, _e
                    )
        else:
            logging.getLogger(__name__).info("Phase 2 recovery: no stuck files found")

    await _recover_phase2()

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    from app.services.classroom_rag import classroom_rag_service
    from app.rag.storage.postgres_kv import close_pool

    await app.state.connection_manager.stop()
    if os.getenv("WS_FANOUT", "memory") == "redis":
        from app.realtime.redis_client import close_redis as _close_redis
        await _close_redis()

    await classroom_rag_service.finalize_all()
    await close_pool()


app = FastAPI(title="Learning SAMpai API", lifespan=lifespan)

origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(classroom.router)
app.include_router(folder.router)
app.include_router(file.router)
app.include_router(chat.router)
app.include_router(quiz.router)
app.include_router(flashcards_router.router)
app.include_router(group_chat_router.router)
app.include_router(mindmap_router.router)
app.include_router(announcements_router.router)


@app.get("/")
def root():
    return {
        "message": "Learning SAMpai API v3.0 — LightRAG + Multimodal",
        "features": [
            "Graph-based multi-hop RAG (LightRAG)",
            "Multimodal document ingestion (Docling)",
            "Image / table / equation understanding",
            "Persistent conversation history",
            "Topic extraction for UI",
        ],
    }
