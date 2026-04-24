"""
ChromaDB vector storage adapter implementing BaseVectorStorage.
Replaces LangChain's Chroma wrapper with a direct chromadb.PersistentClient.

Collection naming convention: {workspace}__{namespace}
Example: classroom_7__entities, classroom_7__relationships, classroom_7__chunks
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import chromadb
import numpy as np

from app.rag.base import BaseVectorStorage
from app.rag.utils import logger

# Module-level singleton client
_chroma_client: chromadb.PersistentClient | None = None


def _get_chroma_client() -> chromadb.PersistentClient:
    global _chroma_client
    if _chroma_client is None:
        chroma_dir = os.getenv("CHROMA_DATA_DIR", "./chroma_data")
        _chroma_client = chromadb.PersistentClient(path=chroma_dir)
        logger.info(f"ChromaDB PersistentClient initialized at {chroma_dir}")
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
    ) -> list[dict[str, Any]]:
        """Query vector storage, returns top_k results with metadata."""
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

        logger.debug(
            "[%s/%s] query: top_k=%d collection_count=%d query='%s...'",
            self.workspace, self.namespace, top_k, count, query[:40],
        )
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, count),
            include=["documents", "metadatas", "distances"],
        )

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

            item = {"id": doc_id, "content": doc, "distance": distance, **meta}
            output.append(item)

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
