"""
Must be imported before any app.* or chromadb import.

1. Patches NumPy 2.x removed aliases (chromadb 0.4.24 references them).
2. Sets host-accessible service URLs via os.environ.setdefault() BEFORE
   load_dotenv(), so .env.docker's Docker-internal hostnames (db:5432,
   neo4j:7687) cannot overwrite them.
3. Loads .env.docker (or .env) with override=False to pick up OPENAI_API_KEY
   without clobbering the URLs set above.
"""
import numpy as np

if not hasattr(np, "float_"):
    np.float_ = np.float64
if not hasattr(np, "int_"):
    np.int_ = np.intp
if not hasattr(np, "bool_"):
    np.bool_ = np.bool8

import os
import pathlib

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:password@localhost:5433/Learning_SAMpai_db",
)
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USERNAME", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "sampai_neo4j_password")
os.environ.setdefault("CHROMA_HOST", "localhost")
os.environ.setdefault("CHROMA_PORT", "8001")
os.environ.setdefault("SECRET_KEY", "benchmark-dummy-secret")

from dotenv import load_dotenv  # noqa: E402

_root = pathlib.Path(__file__).resolve().parent.parent.parent.parent
for _candidate in (
    _root / ".env.docker",
    _root / ".env",
    pathlib.Path(".env.docker"),
    pathlib.Path(".env"),
):
    if _candidate.exists():
        load_dotenv(_candidate, override=False)
        break
