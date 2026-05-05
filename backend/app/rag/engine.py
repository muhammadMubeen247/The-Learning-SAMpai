"""
LightRAGEngine: Per-classroom orchestrator for the RAG pipeline.

Responsibilities:
  - Initialize and hold all storage objects (KV × 7, Vector × 3, Graph × 1, DocStatus × 1)
  - ainsert(): chunk → embed → extract entities → merge → store
  - aquery(): dispatch to kg_query or naive_query based on mode
  - adelete_file(): remove all vectors/graph nodes/KV records for a file
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from typing import Literal

from app.rag.base import (
    BaseGraphStorage,
    BaseKVStorage,
    BaseVectorStorage,
    DeletionResult,
    DocProcessingStatus,
    DocStatus,
    DocStatusStorage,
    QueryParam,
    QueryResult,
)
from app.rag.constants import (
    BACKGROUND_MAX_ASYNC,
    DEFAULT_CHUNK_OVERLAP_TOKEN_SIZE,
    DEFAULT_CHUNK_TOKEN_SIZE,
    DEFAULT_ENTITY_TYPES,
    DEFAULT_FORCE_LLM_SUMMARY_ON_MERGE,
    DEFAULT_MAX_ASYNC,
    DEFAULT_MAX_EXTRACT_INPUT_TOKENS,
    DEFAULT_MAX_GLEANING,
    DEFAULT_MAX_SOURCE_IDS_PER_ENTITY,
    DEFAULT_MAX_SOURCE_IDS_PER_RELATION,
    DEFAULT_SOURCE_IDS_LIMIT_METHOD,
    DEFAULT_SUMMARY_CONTEXT_SIZE,
    DEFAULT_SUMMARY_LANGUAGE,
    DEFAULT_SUMMARY_LENGTH_RECOMMENDED,
    DEFAULT_SUMMARY_MAX_TOKENS,
    GRAPH_FIELD_SEP,
)
from app.rag.namespace import NameSpace
from app.rag.operate import (
    chunking_by_token_size,
    extract_entities,
    kg_query,
    merge_nodes_and_edges,
    naive_query,
)
from app.rag.storage.chroma_vector import ChromaVectorStorage
from app.rag.storage.neo4j_graph import Neo4jGraphStorage
from app.rag.storage.postgres_doc_status import PostgresDocStatusStorage
from app.rag.storage.postgres_kv import PostgresKVStorage
from app.rag.utils import (
    TiktokenTokenizer,
    compute_mdhash_id,
    logger,
    openai_embedding_func,
    openai_llm_func,
)


@dataclass
class LightRAGEngine:
    """
    Per-classroom LightRAG engine.

    Usage::

        engine = LightRAGEngine(workspace="classroom_7")
        await engine.initialize()

        await engine.ainsert("Full text content...", file_paths=["lecture1.pdf"])
        result = await engine.aquery("What is Newton's second law?", QueryParam(mode="mix"))

        await engine.finalize()
    """

    workspace: str  # e.g. "classroom_7"

    # ------------------------------------------------------------------
    # Injected storage objects (set during initialize())
    # ------------------------------------------------------------------
    _full_docs: PostgresKVStorage = field(init=False, default=None)
    _text_chunks: PostgresKVStorage = field(init=False, default=None)
    _llm_cache: PostgresKVStorage = field(init=False, default=None)
    _full_entities: PostgresKVStorage = field(init=False, default=None)
    _full_relations: PostgresKVStorage = field(init=False, default=None)
    _entity_chunks: PostgresKVStorage = field(init=False, default=None)
    _relation_chunks: PostgresKVStorage = field(init=False, default=None)
    _entities_vdb: ChromaVectorStorage = field(init=False, default=None)
    _relationships_vdb: ChromaVectorStorage = field(init=False, default=None)
    _chunks_vdb: ChromaVectorStorage = field(init=False, default=None)
    _graph: Neo4jGraphStorage = field(init=False, default=None)
    _doc_status: PostgresDocStatusStorage = field(init=False, default=None)
    _initialized: bool = field(init=False, default=False)

    # ------------------------------------------------------------------

    def _make_global_config(self, background: bool = False) -> dict[str, Any]:
        """Assemble the global_config dict that operate.py functions expect.

        Args:
            background: When True, uses BACKGROUND_MAX_ASYNC instead of the
                default so Phase 2 ingestion yields headroom to interactive
                callers (chat, flashcards) in the shared OpenAI rate-limit bucket.
        """
        return {
            # LLM / embedding
            "llm_model_func": openai_llm_func,
            "embedding_func": openai_embedding_func,
            # Tokenizer
            "tokenizer": TiktokenTokenizer(),
            # Entity extraction
            "entity_extract_max_gleaning": DEFAULT_MAX_GLEANING,
            "max_extract_input_tokens": DEFAULT_MAX_EXTRACT_INPUT_TOKENS,
            # Description summarization
            "summary_context_size": DEFAULT_SUMMARY_CONTEXT_SIZE,
            "summary_max_tokens": DEFAULT_SUMMARY_MAX_TOKENS,
            "summary_length_recommended": DEFAULT_SUMMARY_LENGTH_RECOMMENDED,
            "force_llm_summary_on_merge": DEFAULT_FORCE_LLM_SUMMARY_ON_MERGE,
            # Source ID limits
            "max_source_ids_per_entity": DEFAULT_MAX_SOURCE_IDS_PER_ENTITY,
            "max_source_ids_per_relation": DEFAULT_MAX_SOURCE_IDS_PER_RELATION,
            "source_ids_limit_method": DEFAULT_SOURCE_IDS_LIMIT_METHOD,
            # Concurrency — background inserts use a lower limit to leave
            # headroom for interactive foreground API calls
            "llm_model_max_async": BACKGROUND_MAX_ASYNC if background else DEFAULT_MAX_ASYNC,
            # Workspace
            "workspace": self.workspace,
            # Add-on params (language, entity types)
            "addon_params": {
                "language": DEFAULT_SUMMARY_LANGUAGE,
                "entity_types": DEFAULT_ENTITY_TYPES,
            },
            # Storage references (used by some operate.py helpers)
            "llm_response_cache": self._llm_cache,
        }

    async def initialize(self) -> None:
        """Create and initialize all storage objects."""
        if self._initialized:
            return

        ws = self.workspace
        emb = openai_embedding_func

        # KV storage (7 namespaces)
        def _kv(ns: str) -> PostgresKVStorage:
            return PostgresKVStorage(workspace=ws, namespace=ns, global_config={})

        self._full_docs = _kv(NameSpace.KV_STORE_FULL_DOCS)
        self._text_chunks = _kv(NameSpace.KV_STORE_TEXT_CHUNKS)
        self._llm_cache = _kv(NameSpace.KV_STORE_LLM_RESPONSE_CACHE)
        self._full_entities = _kv(NameSpace.KV_STORE_FULL_ENTITIES)
        self._full_relations = _kv(NameSpace.KV_STORE_FULL_RELATIONS)
        self._entity_chunks = _kv(NameSpace.KV_STORE_ENTITY_CHUNKS)
        self._relation_chunks = _kv(NameSpace.KV_STORE_RELATION_CHUNKS)

        # Vector storage (3 namespaces)
        def _vdb(ns: str) -> ChromaVectorStorage:
            return ChromaVectorStorage(
                workspace=ws, namespace=ns, global_config={}, embedding_func=emb
            )

        self._entities_vdb = _vdb(NameSpace.VECTOR_STORE_ENTITIES)
        self._relationships_vdb = _vdb(NameSpace.VECTOR_STORE_RELATIONSHIPS)
        self._chunks_vdb = _vdb(NameSpace.VECTOR_STORE_CHUNKS)

        # Graph storage
        self._graph = Neo4jGraphStorage(
            workspace=ws,
            namespace=NameSpace.GRAPH_STORE_CHUNK_ENTITY_RELATION,
            global_config={},
            embedding_func=emb,
        )

        # Doc status storage
        self._doc_status = PostgresDocStatusStorage(
            workspace=ws,
            namespace=NameSpace.DOC_STATUS,
            global_config={},
        )

        # Initialize all storages concurrently
        await asyncio.gather(
            self._full_docs.initialize(),
            self._text_chunks.initialize(),
            self._llm_cache.initialize(),
            self._full_entities.initialize(),
            self._full_relations.initialize(),
            self._entity_chunks.initialize(),
            self._relation_chunks.initialize(),
            self._entities_vdb.initialize(),
            self._relationships_vdb.initialize(),
            self._chunks_vdb.initialize(),
            self._graph.initialize(),
            self._doc_status.initialize(),
        )
        self._initialized = True
        logger.info(f"LightRAGEngine initialized for workspace={ws}")

    async def finalize(self) -> None:
        """Close storage connections."""
        if not self._initialized:
            return
        await asyncio.gather(
            self._full_docs.finalize(),
            self._text_chunks.finalize(),
            self._llm_cache.finalize(),
            self._full_entities.finalize(),
            self._full_relations.finalize(),
            self._entity_chunks.finalize(),
            self._relation_chunks.finalize(),
            self._entities_vdb.finalize(),
            self._relationships_vdb.finalize(),
            self._chunks_vdb.finalize(),
            self._graph.finalize(),
            self._doc_status.finalize(),
        )
        self._initialized = False
        logger.info(f"LightRAGEngine finalized for workspace={self.workspace}")

    # ------------------------------------------------------------------
    # Insert pipeline
    # ------------------------------------------------------------------

    async def ainsert(
        self,
        content: str | list[str],
        file_paths: list[str] | None = None,
        split_by_character: str | None = None,
        split_by_character_only: bool = False,
        phase: Literal["full", "phase1", "phase2"] = "full",
    ) -> None:
        """
        Chunk, embed, and index text content into the knowledge graph.

        Args:
            content: Single document string or list of document strings.
            file_paths: Parallel list of source file paths (for citation/metadata).
                        Must match length of `content` list if provided.
            split_by_character: Optional character to split by before token chunking.
            split_by_character_only: If True, don't further split oversized character chunks.
            phase: Processing phase.
                - "full"   — complete pipeline (chunks + entity extraction + KG merge).
                - "phase1" — chunks + embeddings only (enables naive-mode features).
                - "phase2" — entity extraction + KG merge only (enables mix-mode features).
                  For phase2, content is still required to recompute the doc_id for
                  idempotency checks; chunks must already exist from a prior phase1 call.
        """
        if not self._initialized:
            await self.initialize()

        if isinstance(content, str):
            content = [content]
        if file_paths is None:
            file_paths = ["unknown_source"] * len(content)
        if len(file_paths) != len(content):
            raise ValueError("file_paths must match content length")

        _insert_t0 = time.time()
        logger.info(
            "ainsert: starting phase=%s — %d document(s) for workspace=%s",
            phase, len(content), self.workspace,
        )

        # Insert is always background work — use the lower concurrency ceiling
        # so active chat/flashcard calls keep headroom in the rate-limit bucket.
        global_config = self._make_global_config(background=True)
        tokenizer = global_config["tokenizer"]

        for doc_text, file_path in zip(content, file_paths):
            await self._insert_single_document(
                doc_text,
                file_path,
                global_config,
                tokenizer,
                split_by_character=split_by_character,
                split_by_character_only=split_by_character_only,
                phase=phase,
            )

        logger.info(
            "ainsert: complete phase=%s in %.2fs — %d document(s) for workspace=%s",
            phase, time.time() - _insert_t0, len(content), self.workspace,
        )

    async def _insert_single_document(
        self,
        content: str,
        file_path: str,
        global_config: dict,
        tokenizer: Any,
        split_by_character: str | None = None,
        split_by_character_only: bool = False,
        phase: Literal["full", "phase1", "phase2"] = "full",
    ) -> None:
        """Insert pipeline for a single document, optionally split into phases.

        phase="phase1" — stores chunks + embeddings, sets DocStatus.CHUNKS_READY.
        phase="phase2" — runs entity extraction + KG merge on existing chunks.
        phase="full"   — both phases in sequence (original behaviour).
        """
        doc_id = compute_mdhash_id(content, prefix="doc-")
        _doc_t0 = time.time()
        logger.info(
            "_insert_single_document: START phase=%s doc_id=%s file=%s content_len=%d",
            phase, doc_id, file_path, len(content),
        )

        try:
            if phase in ("full", "phase1"):
                # ── Phase 1: chunk + embed ─────────────────────────────────
                already = await self._full_docs.get_by_id(doc_id)
                if already is not None and phase == "full":
                    logger.info(f"Document already indexed: {file_path} ({doc_id})")
                    return

                await self._doc_status.set_status(
                    doc_id, DocStatus.PROCESSING,
                    file_path=file_path,
                    content_summary=content[:200],
                    content_length=len(content),
                )

                await self._full_docs.upsert({doc_id: {"content": content, "file_path": file_path}})

                raw_chunks = chunking_by_token_size(
                    tokenizer,
                    content,
                    split_by_character=split_by_character,
                    split_by_character_only=split_by_character_only,
                    chunk_overlap_token_size=DEFAULT_CHUNK_OVERLAP_TOKEN_SIZE,
                    chunk_token_size=DEFAULT_CHUNK_TOKEN_SIZE,
                )

                chunks: dict[str, dict] = {}
                chunk_ids: list[str] = []
                for chunk in raw_chunks:
                    chunk_content = chunk["content"]
                    chunk_id = compute_mdhash_id(chunk_content, prefix="chunk-")
                    chunks[chunk_id] = {
                        "content": chunk_content,
                        "tokens": chunk["tokens"],
                        "chunk_order_index": chunk["chunk_order_index"],
                        "full_doc_id": doc_id,
                        "file_path": file_path,
                    }
                    chunk_ids.append(chunk_id)

                if not chunks:
                    logger.warning(f"No chunks generated for {file_path}")
                    await self._doc_status.set_status(
                        doc_id, DocStatus.FAILED,
                        file_path=file_path, error_msg="No chunks generated",
                    )
                    return

                new_chunk_ids = await self._text_chunks.filter_keys(set(chunk_ids))
                new_chunks = {cid: chunks[cid] for cid in new_chunk_ids}
                logger.info(
                    "_insert_single_document: %d new chunks to index (%d already exist) for %s",
                    len(new_chunks), len(chunks) - len(new_chunks), file_path,
                )

                if new_chunks:
                    vdb_payload: dict[str, dict] = {}
                    for cid, chunk_data in new_chunks.items():
                        vdb_payload[cid] = {
                            "content": chunk_data["content"],
                            "file_path": file_path,
                            "full_doc_id": doc_id,
                            "chunk_order_index": chunk_data["chunk_order_index"],
                        }
                    await self._chunks_vdb.upsert(vdb_payload)
                    await self._text_chunks.upsert(new_chunks)
                    logger.info(
                        "Indexed %d new chunks (%d total) for %s",
                        len(new_chunks), len(chunks), file_path,
                    )

                if phase == "phase1":
                    # Signal that naive-mode features are now usable.
                    await self._doc_status.set_status(
                        doc_id, DocStatus.CHUNKS_READY,
                        file_path=file_path,
                        content_summary=content[:200],
                        content_length=len(content),
                        chunks_count=len(chunks),
                        chunks_list=list(chunks.keys()),
                    )
                    logger.info(
                        "_insert_single_document: phase1 complete in %.2fs — %s",
                        time.time() - _doc_t0, file_path,
                    )
                    return

            # ── Phase 2: entity extraction + KG merge ─────────────────────
            # Retrieve new_chunks from KV if we are resuming from a phase1 call.
            if phase == "phase2":
                doc_record = await self._doc_status.get_doc_by_file_path(file_path)
                stored_chunk_ids: list[str] = (doc_record or {}).get("chunks_list") or []
                if not stored_chunk_ids:
                    # Fallback: recompute chunk IDs from content
                    raw_chunks_p2 = chunking_by_token_size(
                        tokenizer, content,
                        split_by_character=split_by_character,
                        split_by_character_only=split_by_character_only,
                        chunk_overlap_token_size=DEFAULT_CHUNK_OVERLAP_TOKEN_SIZE,
                        chunk_token_size=DEFAULT_CHUNK_TOKEN_SIZE,
                    )
                    stored_chunk_ids = [
                        compute_mdhash_id(c["content"], prefix="chunk-") for c in raw_chunks_p2
                    ]
                new_chunks = {}
                if stored_chunk_ids:
                    rows = await self._text_chunks.get_by_ids(stored_chunk_ids)
                    new_chunks = {r["id"]: r for r in rows if r}

            if new_chunks:
                logger.info(
                    "_insert_single_document: entity extraction on %d chunks for %s",
                    len(new_chunks), file_path,
                )
                chunk_results = await extract_entities(
                    new_chunks, global_config, llm_response_cache=self._llm_cache,
                )
                await merge_nodes_and_edges(
                    chunk_results=chunk_results,
                    knowledge_graph_inst=self._graph,
                    entity_vdb=self._entities_vdb,
                    relationships_vdb=self._relationships_vdb,
                    global_config=global_config,
                    full_entities_storage=self._full_entities,
                    full_relations_storage=self._full_relations,
                    doc_id=doc_id,
                    llm_response_cache=self._llm_cache,
                    entity_chunks_storage=self._entity_chunks,
                    relation_chunks_storage=self._relation_chunks,
                    file_path=file_path,
                )

            # Resolve chunks/chunk_ids for the final status write
            if phase == "phase2":
                final_chunks_list = stored_chunk_ids
                final_chunks_count = len(stored_chunk_ids)
            else:
                final_chunks_list = list(chunks.keys())  # type: ignore[possibly-undefined]
                final_chunks_count = len(chunks)         # type: ignore[possibly-undefined]

            await self._doc_status.set_status(
                doc_id, DocStatus.PROCESSED,
                file_path=file_path,
                content_summary=content[:200],
                content_length=len(content),
                chunks_count=final_chunks_count,
                chunks_list=final_chunks_list,
            )
            logger.info(
                "_insert_single_document: complete phase=%s in %.2fs — %s (%s)",
                phase, time.time() - _doc_t0, file_path, doc_id,
            )

        except Exception as e:
            logger.error(
                "Document processing failed phase=%s for %s: %s", phase, file_path, e,
                exc_info=True,
            )
            await self._doc_status.set_status(
                doc_id, DocStatus.FAILED, file_path=file_path, error_msg=str(e),
            )
            raise

    # ------------------------------------------------------------------
    # Query pipeline
    # ------------------------------------------------------------------

    async def aquery(
        self,
        query: str,
        param: QueryParam | None = None,
    ) -> QueryResult:
        """
        Query the knowledge base. Returns a QueryResult with content and reference_list.

        Args:
            query: The user's question.
            param: QueryParam controlling mode, top_k, history, etc.
                   Defaults to mix mode if None.
        """
        if not self._initialized:
            await self.initialize()

        if param is None:
            param = QueryParam(mode="mix")

        _query_t0 = time.time()
        logger.info(
            "aquery: START mode=%s query='%s...' workspace=%s",
            param.mode, query[:60], self.workspace,
        )
        global_config = self._make_global_config()

        if param.mode == "naive":
            result = await naive_query(
                query=query,
                chunks_vdb=self._chunks_vdb,
                query_param=param,
                global_config=global_config,
                hashing_kv=self._llm_cache,
            )
        else:
            # mix / local / global / hybrid — all go through kg_query
            result = await kg_query(
                query=query,
                knowledge_graph_inst=self._graph,
                entities_vdb=self._entities_vdb,
                relationships_vdb=self._relationships_vdb,
                text_chunks_db=self._text_chunks,
                query_param=param,
                global_config=global_config,
                hashing_kv=self._llm_cache,
                chunks_vdb=self._chunks_vdb,
                entity_chunks_db=self._entity_chunks,
            )

        if result is None:
            logger.info(
                "aquery: no result in %.2fs mode=%s workspace=%s",
                time.time() - _query_t0, param.mode, self.workspace,
            )
            return QueryResult(
                content="I don't have enough information in the knowledge base to answer this question.",
                raw_data={"data": {"references": []}},
            )

        logger.info(
            "aquery: complete in %.2fs mode=%s result_len=%d workspace=%s",
            time.time() - _query_t0, param.mode,
            len(result.content) if result.content else 0,
            self.workspace,
        )
        return result

    # ------------------------------------------------------------------
    # Deletion pipeline
    # ------------------------------------------------------------------

    async def adelete_file(self, file_path: str) -> DeletionResult:
        """
        Remove all knowledge derived from a specific file.

        Steps:
          1. Find doc_id from doc_status
          2. Collect chunk IDs from full_docs
          3. Delete chunks from KV + vector stores
          4. Collect entities/relations linked only to this file
          5. Delete those from graph + vector stores
          6. Remove doc from full_docs, full_entities, full_relations
          7. Update doc_status to FAILED/removed
        """
        if not self._initialized:
            await self.initialize()

        # Find document record
        doc_record = await self._doc_status.get_doc_by_file_path(file_path)
        if doc_record is None:
            return DeletionResult(
                status="not_found",
                doc_id="",
                message=f"No document found for file_path={file_path}",
                status_code=404,
                file_path=file_path,
            )

        doc_id = doc_record.get("doc_id", "")
        if not doc_id:
            return DeletionResult(
                status="fail",
                doc_id="",
                message="doc_id missing from status record",
                file_path=file_path,
            )

        try:
            # Get chunk IDs for this document
            chunk_ids: list[str] = doc_record.get("chunks_list") or []
            if not chunk_ids:
                # Fallback: recompute from full_docs
                full_doc = await self._full_docs.get_by_id(doc_id)
                if full_doc:
                    content = full_doc.get("content", "")
                    global_config = self._make_global_config()
                    tokenizer = global_config["tokenizer"]
                    raw_chunks = chunking_by_token_size(
                        tokenizer, content,
                        chunk_overlap_token_size=DEFAULT_CHUNK_OVERLAP_TOKEN_SIZE,
                        chunk_token_size=DEFAULT_CHUNK_TOKEN_SIZE,
                    )
                    chunk_ids = [
                        compute_mdhash_id(c["content"], prefix="chunk-") for c in raw_chunks
                    ]

            # 1. Delete chunks from vector store + KV
            if chunk_ids:
                await asyncio.gather(
                    self._chunks_vdb.delete(chunk_ids),
                    self._text_chunks.delete(chunk_ids),
                )

            # 2. Find entities associated with this doc
            entities_record = await self._full_entities.get_by_id(doc_id)
            entity_names: list[str] = []
            if entities_record:
                entity_names = entities_record.get("entity_names", [])

            # 3. Delete entity VDB entries
            if entity_names:
                entity_vdb_ids = [
                    compute_mdhash_id(name, prefix="ent-") for name in entity_names
                ]
                await self._entities_vdb.delete(entity_vdb_ids)
                # Delete graph nodes (which cascades to edges in Neo4j)
                await asyncio.gather(*[
                    self._graph.delete_node(name) for name in entity_names
                ])

            # 4. Find relations associated with this doc
            relations_record = await self._full_relations.get_by_id(doc_id)
            if relations_record:
                relation_pairs = relations_record.get("relation_pairs", [])
                rel_vdb_ids = [
                    compute_mdhash_id(pair[0] + pair[1], prefix="rel-")
                    for pair in relation_pairs
                    if len(pair) == 2
                ]
                if rel_vdb_ids:
                    await self._relationships_vdb.delete(rel_vdb_ids)

            # 5. Clean up KV records
            await asyncio.gather(
                self._full_docs.delete([doc_id]),
                self._full_entities.delete([doc_id]),
                self._full_relations.delete([doc_id]),
                self._entity_chunks.delete(entity_names) if entity_names else asyncio.sleep(0),
            )

            # 6. Update doc status
            await self._doc_status.delete([doc_id])

            logger.info(
                f"Deleted file {file_path}: {len(chunk_ids)} chunks, "
                f"{len(entity_names)} entities"
            )
            return DeletionResult(
                status="success",
                doc_id=doc_id,
                message=(
                    f"Deleted {len(chunk_ids)} chunks and {len(entity_names)} entities"
                ),
                file_path=file_path,
            )

        except Exception as e:
            logger.error(f"adelete_file failed for {file_path}: {e}", exc_info=True)
            return DeletionResult(
                status="fail",
                doc_id=doc_id,
                message=str(e),
                file_path=file_path,
            )

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    async def get_doc_status(self, file_path: str) -> DocProcessingStatus | None:
        """Return processing status for a file, or None if not found."""
        record = await self._doc_status.get_doc_by_file_path(file_path)
        if record is None:
            return None
        return DocProcessingStatus(
            content_summary=record.get("content_summary", ""),
            content_length=record.get("content_length", 0),
            file_path=record.get("file_path", file_path),
            status=DocStatus(record.get("status", DocStatus.PENDING.value)),
            created_at=str(record.get("created_at", "")),
            updated_at=str(record.get("updated_at", "")),
            track_id=record.get("doc_id"),
            chunks_count=record.get("chunks_count"),
            chunks_list=record.get("chunks_list") or [],
            error_msg=record.get("error_msg"),
        )

    async def is_empty(self) -> bool:
        """Return True if no documents have been indexed."""
        return await self._full_docs.is_empty()
