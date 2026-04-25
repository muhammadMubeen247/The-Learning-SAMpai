"""
ChromaDB vector storage adapter implementing BaseVectorStorage.

Uses chromadb.HttpClient against a standalone chroma container (see
docker-compose.yml). HttpClient sidesteps the hnswlib native binary (.pyd)
that PersistentClient loads in-process — that binary is unsigned and is
blocked by Windows Smart App Control on some dev machines. The server in
Docker has the binary and accepts plain HTTP requests.

Telemetry is disabled via Settings(anonymized_telemetry=False) to eliminate
the `posthog.capture() takes 1 positional argument but 3 were given` error
caused by the chromadb 0.4.24 / posthog 7.x ABI mismatch.

Collection naming convention: {workspace}__{namespace}
Example: classroom_7__entities, classroom_7__relationships, classroom_7__chunks
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import chromadb
from chromadb.config import Settings
import numpy as np

from app.rag.base import BaseVectorStorage
from app.rag.utils import logger

# Module-level singleton client
_chroma_client: chromadb.ClientAPI | None = None


def _get_chroma_client() -> chromadb.ClientAPI:
    global _chroma_client
    if _chroma_client is None:
        host = os.getenv("CHROMA_HOST", "localhost")
        port = int(os.getenv("CHROMA_PORT", "8001"))
        _chroma_client = chromadb.HttpClient(
            host=host,
            port=port,
            settings=Settings(anonymized_telemetry=False),
        )
        logger.info(f"ChromaDB HttpClient initialized at http://{host}:{port}")
    return _chroma_client


@dataclass
class ChromaVectorStorage(BaseVectorStorage):
    """
    Vector storage using ChromaDB with one collection per (workspace, namespace).

    Metadata stored per document (varies by namespace):
      - entities: entity_name, source_id, content, file_path
      - relationships: src_id, tgt_id, source_id, content, file_path
      - chunks: full_doc_id, content, file_path
    """

    embedding_func: Any = field(default=None)
    cosine_better_than_threshold: float = field(default=0.2)
    meta_fields: set[str] = field(default_factory=set)

    def __post_init__(self):
        self._collection_name = f"{self.workspace}__{self.namespace}"

    def _get_collection(self) -> chromadb.Collection:
        client = _get_chroma_client()
        return client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    async def initialize(self):
        self._get_collection()  # Ensure collection exists

    async def finalize(self):
        pass

    async def index_done_callback(self) -> None:
        pass  # ChromaDB persists writes immediately

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    async def upsert(self, data: dict[str, dict[str, Any]]) -> None:
        """
        Insert or update vectors.
        data: {id: {"content": str, "entity_name"?: str, ...}}
        """
        if not data:
            return

        collection = self._get_collection()
        ids = list(data.keys())
        documents = []
        metadatas = []

        for doc_id in ids:
            item = data[doc_id]
            content = item.get("content", "")
            documents.append(content)

            # Build metadata (exclude content and large fields)
            meta = {}
            for k, v in item.items():
                if k == "content":
                    continue
                if v is None:
                    meta[k] = ""
                elif isinstance(v, (str, int, float, bool)):
                    meta[k] = v
                else:
                    meta[k] = str(v)
            metadatas.append(meta)

        logger.debug(
            "[%s/%s] upsert: %d vectors to ChromaDB", self.workspace, self.namespace, len(ids)
        )
        # Batch embed
        embeddings_array = await self.embedding_func(documents)
        embeddings = embeddings_array.tolist()

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        logger.debug(
            "[%s/%s] upsert done — collection now has %d total items",
            self.workspace, self.namespace, collection.count(),
        )

    async def query(
        self,
        query: str,
        top_k: int,
        query_embedding: list[float] | None = None,
        file_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query vector storage, returns top_k results with metadata.

        file_filter: when set, restrict results to items originating from
        this file_path. For the ``chunks`` namespace each item carries a
        single canonical file_path → use Chroma's native ``where`` clause.
        For ``entities``/``relationships`` an item's file_path may be a
        GRAPH_FIELD_SEP-joined list of files contributing to the merged
        record, so we over-fetch and post-filter in Python.
        """
        from app.rag.constants import GRAPH_FIELD_SEP

        collection = self._get_collection()

        if query_embedding is None:
            emb_array = await self.embedding_func([query])
            query_embedding = emb_array[0].tolist()

        count = collection.count()
        if count == 0:
            logger.debug(
                "[%s/%s] query: collection empty, returning []",
                self.workspace, self.namespace,
            )
            return []

        # Decide retrieval strategy based on file_filter and namespace.
        # `chunks` stores a single file_path per row → native filter is exact.
        # `entities`/`relationships` may store a joined list → over-fetch and
        # post-filter on the python side.
        use_native_where = file_filter is not None and self.namespace == "chunks"
        post_filter = file_filter is not None and not use_native_where

        # Over-fetch when post-filtering so we don't drop below top_k.
        fetch_n = top_k * 4 if post_filter else top_k
        n_results = min(fetch_n, count)

        logger.debug(
            "[%s/%s] query: top_k=%d fetch_n=%d collection_count=%d "
            "file_filter=%s query='%s...'",
            self.workspace, self.namespace, top_k, fetch_n, count,
            "yes" if file_filter else "no", query[:40],
        )
        query_kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if use_native_where:
            query_kwargs["where"] = {"file_path": file_filter}
        results = collection.query(**query_kwargs)

        if not results["ids"] or not results["ids"][0]:
            return []

        output = []
        for i, doc_id in enumerate(results["ids"][0]):
            distance = results["distances"][0][i] if results["distances"] else 1.0
            # ChromaDB cosine distance: 0 = identical, 2 = opposite
            # Convert to similarity: 1 - (distance / 2) approximates cosine similarity
            similarity = 1.0 - (distance / 2.0)
            if similarity < self.cosine_better_than_threshold:
                continue

            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            doc = results["documents"][0][i] if results["documents"] else ""

            if post_filter:
                stored_fp = (meta.get("file_path") or "") if meta else ""
                stored_paths = [p for p in stored_fp.split(GRAPH_FIELD_SEP) if p]
                if file_filter not in stored_paths:
                    continue

            item = {"id": doc_id, "content": doc, "distance": distance, **meta}
            output.append(item)
            if len(output) >= top_k:
                break

        logger.debug(
            "[%s/%s] query: returned %d results (threshold=%.2f)",
            self.workspace, self.namespace, len(output), self.cosine_better_than_threshold,
        )
        return output

    async def delete_entity(self, entity_name: str) -> None:
        """Delete a single entity by name (searches metadata)."""
        collection = self._get_collection()
        try:
            results = collection.get(where={"entity_name": entity_name})
            if results["ids"]:
                collection.delete(ids=results["ids"])
        except Exception as e:
            logger.warning(f"delete_entity({entity_name}) error: {e}")

    async def delete_entity_relation(self, entity_name: str) -> None:
        """Delete all relations involving an entity (both src and tgt)."""
        collection = self._get_collection()
        try:
            # Try deleting where entity is the source
            results_src = collection.get(where={"src_id": entity_name})
            results_tgt = collection.get(where={"tgt_id": entity_name})
            ids_to_delete = list(set(results_src["ids"] + results_tgt["ids"]))
            if ids_to_delete:
                collection.delete(ids=ids_to_delete)
        except Exception as e:
            logger.warning(f"delete_entity_relation({entity_name}) error: {e}")

    async def get_by_id(self, id: str) -> dict[str, Any] | None:
        collection = self._get_collection()
        try:
            results = collection.get(ids=[id], include=["documents", "metadatas"])
            if not results["ids"]:
                return None
            meta = results["metadatas"][0] if results["metadatas"] else {}
            doc = results["documents"][0] if results["documents"] else ""
            return {"id": id, "content": doc, **meta}
        except Exception as e:
            logger.warning("[%s/%s] get_by_id(%s) error: %s", self.workspace, self.namespace, id, e)
            return None

    async def get_by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        if not ids:
            return []
        collection = self._get_collection()
        try:
            results = collection.get(ids=ids, include=["documents", "metadatas"])
            output = []
            for i, doc_id in enumerate(results["ids"]):
                meta = results["metadatas"][i] if results["metadatas"] else {}
                doc = results["documents"][i] if results["documents"] else ""
                output.append({"id": doc_id, "content": doc, **meta})
            return output
        except Exception as e:
            logger.warning("[%s/%s] get_by_ids(%d ids) error: %s", self.workspace, self.namespace, len(ids), e)
            return []

    async def delete(self, ids: list[str]) -> None:
        if not ids:
            return
        collection = self._get_collection()
        collection.delete(ids=ids)

    async def get_vectors_by_ids(self, ids: list[str]) -> dict[str, list[float]]:
        """Return raw embeddings by ID (used for reranking). Empty dict if not supported."""
        if not ids:
            return {}
        collection = self._get_collection()
        try:
            results = collection.get(ids=ids, include=["embeddings"])
            return {
                doc_id: emb
                for doc_id, emb in zip(results["ids"], results["embeddings"] or [])
            }
        except Exception:
            return {}

    async def drop(self) -> dict[str, str]:
        try:
            client = _get_chroma_client()
            client.delete_collection(self._collection_name)
            logger.info(f"Dropped ChromaDB collection: {self._collection_name}")
            return {"status": "success", "message": "data dropped"}
        except Exception as e:
            logger.error(f"ChromaVectorStorage drop error: {e}")
            return {"status": "error", "message": str(e)}
