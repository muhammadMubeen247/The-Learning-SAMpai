"""
Root conftest.py — applies to all test sessions.

Sets safe environment variable defaults so that module-level imports
(chromadb client, neo4j driver config, etc.) don't fail when real
services are unavailable during unit testing.
"""
import os

# NumPy 2.x removed np.float_ / np.bool_ / np.int_ etc.
# chromadb 0.4.x and chroma-hnswlib 0.7.x still reference them.
# Patch before any chromadb import happens.
import numpy as np
if not hasattr(np, "float_"):
    np.float_ = np.float64   # type: ignore[attr-defined]
if not hasattr(np, "bool_"):
    np.bool_ = np.bool_      # type: ignore[attr-defined]  # already exists as bool_
if not hasattr(np, "int_"):
    np.int_ = np.intp        # type: ignore[attr-defined]

# Set env defaults before any app modules are imported.
# Integration tests that need real services skip themselves when these
# point to non-existent servers — see test_rag_integration.py.
# These are safe stubs for unit tests only (no real service calls).
# DATABASE_URL and NEO4J_URI are intentionally NOT set here so that
# test_rag_integration.py correctly skips when services are unavailable.
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")
os.environ.setdefault("CHROMA_DATA_DIR", "/tmp/chroma_test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only")
