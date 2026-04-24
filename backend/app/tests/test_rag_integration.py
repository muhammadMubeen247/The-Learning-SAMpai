"""
RAG Pipeline Integration Tests

These tests require real services:
  - PostgreSQL (DATABASE_URL env var)
  - Neo4j (NEO4J_* env vars)
  - ChromaDB (CHROMA_DATA_DIR env var)
  - OpenAI API key (OPENAI_API_KEY env var)

Run:
    pytest app/tests/test_rag_integration.py -v
    pytest app/tests/test_rag_integration.py -v -m "not llm"  # skip LLM-calling tests
"""
from __future__ import annotations

import os
import pytest
import pytest_asyncio

# Skip entire module if required env vars are missing
pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL") or not os.getenv("NEO4J_URI"),
    reason="RAG integration tests require DATABASE_URL and NEO4J_URI",
)

# ---------------------------------------------------------------------------
# Fixtures — function-scoped to avoid asyncio event loop sharing issues.
# Each test gets a fresh engine; this is slower but avoids RuntimeError
# "Future attached to a different loop" when asyncpg/neo4j connections
# are reused across pytest-asyncio's per-function event loops.
# ---------------------------------------------------------------------------

TEST_WORKSPACE = "test_rag_integration_workspace"


async def _cleanup_workspace(eng):
    """Best-effort cleanup of all test data."""
    try:
        from app.rag.storage.postgres_kv import _get_pool
        pool = await _get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM rag_kv_store WHERE workspace = $1", TEST_WORKSPACE
            )
            await conn.execute(
                "DELETE FROM rag_doc_status WHERE workspace = $1", TEST_WORKSPACE
            )
    except Exception:
        pass
    try:
        for vdb in (eng._entities_vdb, eng._relationships_vdb, eng._chunks_vdb):
            await vdb.drop()
    except Exception:
        pass


async def _make_engine():
    """Create and initialize a fresh LightRAGEngine."""
    from app.rag.storage.postgres_kv import close_pool, _get_pool  # noqa: F401
    # Close and reset any pool from a previous test's event loop
    await close_pool()

    from app.rag.engine import LightRAGEngine
    eng = LightRAGEngine(workspace=TEST_WORKSPACE)
    await eng.initialize()
    return eng


async def _teardown_engine(eng):
    from app.rag.storage.postgres_kv import close_pool
    await _cleanup_workspace(eng)
    await eng.finalize()
    await close_pool()


# ---------------------------------------------------------------------------
# Storage layer tests (no LLM)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_postgres_kv_upsert_and_get():
    """KV storage: write and read back a record."""
    eng = await _make_engine()
    try:
        kv = eng._text_chunks
        await kv.upsert({"test_key_1": {"content": "hello world", "tokens": 2}})
        result = await kv.get_by_id("test_key_1")
        assert result is not None
        assert result["content"] == "hello world"
    finally:
        await _teardown_engine(eng)


@pytest.mark.asyncio
async def test_postgres_kv_filter_keys():
    """filter_keys returns only keys not already present."""
    eng = await _make_engine()
    try:
        kv = eng._text_chunks
        await kv.upsert({"existing_key": {"content": "already here", "tokens": 2}})
        new_keys = await kv.filter_keys({"existing_key", "brand_new_key"})
        assert "brand_new_key" in new_keys
        assert "existing_key" not in new_keys
    finally:
        await _teardown_engine(eng)


@pytest.mark.asyncio
async def test_postgres_kv_delete():
    """KV delete removes the record."""
    eng = await _make_engine()
    try:
        kv = eng._text_chunks
        await kv.upsert({"to_delete": {"content": "bye", "tokens": 1}})
        assert await kv.get_by_id("to_delete") is not None
        await kv.delete(["to_delete"])
        assert await kv.get_by_id("to_delete") is None
    finally:
        await _teardown_engine(eng)


@pytest.mark.asyncio
async def test_doc_status_set_and_get():
    """Doc status: set → retrieve by file path."""
    eng = await _make_engine()
    try:
        from app.rag.base import DocStatus
        await eng._doc_status.set_status(
            "doc_test_abc",
            DocStatus.PROCESSED,
            file_path="test_file.pdf",
            content_summary="Test document",
            content_length=100,
            chunks_count=3,
            chunks_list=["c1", "c2", "c3"],
        )
        record = await eng._doc_status.get_doc_by_file_path("test_file.pdf")
        assert record is not None
        assert record["status"] == DocStatus.PROCESSED.value
        assert record["chunks_count"] == 3
    finally:
        await _teardown_engine(eng)


@pytest.mark.asyncio
async def test_neo4j_node_upsert_and_get():
    """Graph: upsert a node, read it back."""
    eng = await _make_engine()
    try:
        graph = eng._graph
        await graph.upsert_node(
            "TestEntity_Integration",
            node_data={
                "entity_id": "TestEntity_Integration",
                "entity_type": "Concept",
                "description": "A test entity for integration testing",
                "source_id": "chunk-test",
                "file_path": "test.pdf",
                "created_at": 0,
            },
        )
        node = await graph.get_node("TestEntity_Integration")
        assert node is not None
        assert node.get("entity_type") == "Concept"
    finally:
        await _teardown_engine(eng)


@pytest.mark.asyncio
async def test_neo4j_edge_upsert_and_get():
    """Graph: upsert an edge between two nodes."""
    eng = await _make_engine()
    try:
        graph = eng._graph
        for name in ("NodeA_Int", "NodeB_Int"):
            await graph.upsert_node(
                name,
                node_data={
                    "entity_id": name,
                    "entity_type": "UNKNOWN",
                    "description": f"Test node {name}",
                    "source_id": "chunk-x",
                    "file_path": "test.pdf",
                    "created_at": 0,
                },
            )
        await graph.upsert_edge(
            "NodeA_Int",
            "NodeB_Int",
            edge_data={
                "weight": 1.5,
                "description": "related to",
                "keywords": "test,edge",
                "source_id": "chunk-x",
                "file_path": "test.pdf",
                "created_at": 0,
            },
        )
        edge = await graph.get_edge("NodeA_Int", "NodeB_Int")
        assert edge is not None
        assert float(edge.get("weight", 0)) == pytest.approx(1.5, rel=0.01)
    finally:
        await _teardown_engine(eng)


@pytest.mark.asyncio
async def test_chroma_vector_upsert_and_query():
    """Vector DB: upsert a document, query it back."""
    eng = await _make_engine()
    try:
        vdb = eng._chunks_vdb
        await vdb.upsert(
            {
                "chunk_test_vec_001": {
                    "content": "The mitochondria is the powerhouse of the cell.",
                    "file_path": "bio.pdf",
                    "full_doc_id": "doc-bio-001",
                }
            }
        )
        results = await vdb.query("cell powerhouse", top_k=5)
        ids = [r.get("id", "") for r in results]
        assert "chunk_test_vec_001" in ids
    finally:
        await _teardown_engine(eng)


# ---------------------------------------------------------------------------
# Pipeline tests (require LLM — marked separately)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.llm
async def test_ainsert_and_aquery_round_trip():
    """
    Full round-trip: insert a short text, query it.
    Requires OpenAI API key.
    """
    from app.rag.base import QueryParam

    eng = await _make_engine()
    try:
        content = (
            "Newton's second law of motion states that Force equals mass times acceleration "
            "(F = ma). This is one of the fundamental laws of classical mechanics."
        )
        await eng.ainsert(content, file_paths=["physics_test.txt"])

        param = QueryParam(mode="naive", top_k=3)
        answer = await eng.aquery("What does Newton's second law state?", param)

        assert isinstance(answer, str)
        assert len(answer) > 20
        assert "newton" in answer.lower() or "force" in answer.lower() or "mass" in answer.lower()
    finally:
        await _teardown_engine(eng)


@pytest.mark.asyncio
@pytest.mark.llm
async def test_adelete_file_removes_chunks():
    """
    Insert a document then delete it — verify chunks are gone.
    """
    eng = await _make_engine()
    try:
        await eng.ainsert(
            "Photosynthesis converts light energy into chemical energy.",
            file_paths=["bio_test.txt"],
        )
        status_before = await eng.get_doc_status("bio_test.txt")
        assert status_before is not None

        result = await eng.adelete_file("bio_test.txt")
        assert result.status == "success"

        status_after = await eng.get_doc_status("bio_test.txt")
        assert status_after is None
    finally:
        await _teardown_engine(eng)
