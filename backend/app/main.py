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

from app.database.init_db import init_db
from app.routes import auth, classroom, folder, file, chat

load_dotenv(
    dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
    override=True,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────
    # Apply our log format AFTER uvicorn's dictConfig has run
    _configure_logging()
    logging.getLogger(__name__).info("Learning SAMpai backend starting up")
    await init_db()

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    from app.services.classroom_rag import classroom_rag_service
    from app.rag.storage.postgres_kv import close_pool

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
