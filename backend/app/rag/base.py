from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable, Dict, List, Literal, Optional, TypedDict, TypeVar

from app.rag.types import KnowledgeGraph


# ---------------------------------------------------------------------------
# Embedding function wrapper (defined here to avoid circular imports;
# the full implementation with __call__ lives in utils.py)
# ---------------------------------------------------------------------------
class EmbeddingFuncProtocol:
    """Minimal protocol so base.py can reference EmbeddingFunc without importing utils."""
    embedding_dim: int


T = TypeVar("T")


# ---------------------------------------------------------------------------
# Core data structures
# ---------------------------------------------------------------------------

class TextChunkSchema(TypedDict):
    tokens: int
    content: str
    full_doc_id: str
    chunk_order_index: int


# ---------------------------------------------------------------------------
# Query parameter dataclass
# ---------------------------------------------------------------------------

@dataclass
class QueryParam:
    """Configuration parameters for query execution."""

    mode: Literal["local", "global", "hybrid", "naive", "mix", "bypass"] = "mix"
    only_need_context: bool = False
    only_need_prompt: bool = False
    response_type: str = "Multiple Paragraphs"
    stream: bool = False

    top_k: int = int(os.getenv("TOP_K", "20"))
    chunk_top_k: int = int(os.getenv("CHUNK_TOP_K", "10"))

    max_entity_tokens: int = int(os.getenv("MAX_ENTITY_TOKENS", "6000"))
    max_relation_tokens: int = int(os.getenv("MAX_RELATION_TOKENS", "8000"))
    max_total_tokens: int = int(os.getenv("MAX_TOTAL_TOKENS", "30000"))

    hl_keywords: list[str] = field(default_factory=list)
    ll_keywords: list[str] = field(default_factory=list)

    conversation_history: list[dict[str, str]] = field(default_factory=list)
    history_turns: int = 0

    model_func: Callable[..., object] | None = None
    user_prompt: str | None = None
    enable_rerank: bool = False
    include_references: bool = False

    # Multi-hop graph traversal
    traversal_hops: int = 2
    max_graph_neighbors: int = 30


# ---------------------------------------------------------------------------
# Storage base classes
# ---------------------------------------------------------------------------

@dataclass
class StorageNameSpace(ABC):
    namespace: str
    workspace: str
    global_config: dict[str, Any]

    async def initialize(self):
        """Initialize the storage."""
        pass

    async def finalize(self):
        """Finalize the storage."""
        pass

    @abstractmethod
    async def index_done_callback(self) -> None:
        """Commit storage operations after indexing."""

    @abstractmethod
    async def drop(self) -> dict[str, str]:
        """Drop all data from storage."""


@dataclass
class BaseVectorStorage(StorageNameSpace, ABC):
    embedding_func: Any  # EmbeddingFunc from utils.py
    cosine_better_than_threshold: float = field(default=0.2)
    meta_fields: set[str] = field(default_factory=set)

    @abstractmethod
    async def query(
        self, query: str, top_k: int, query_embedding: list[float] | None = None
    ) -> list[dict[str, Any]]:
        """Query vector storage and return top_k results."""

    @abstractmethod
    async def upsert(self, data: dict[str, dict[str, Any]]) -> None:
        """Insert or update vectors."""

    @abstractmethod
    async def delete_entity(self, entity_name: str) -> None:
        """Delete a single entity by name."""

    @abstractmethod
    async def delete_entity_relation(self, entity_name: str) -> None:
        """Delete all relations for an entity."""

    @abstractmethod
    async def get_by_id(self, id: str) -> dict[str, Any] | None:
        """Get vector data by ID."""

    @abstractmethod
    async def get_by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        """Get multiple vector data by IDs."""

    @abstractmethod
    async def delete(self, ids: list[str]) -> None:
        """Delete vectors by IDs."""

    @abstractmethod
    async def get_vectors_by_ids(self, ids: list[str]) -> dict[str, list[float]]:
        """Get raw vectors by IDs (for reranking)."""


@dataclass
class BaseKVStorage(StorageNameSpace, ABC):
    embedding_func: Any  # EmbeddingFunc

    @abstractmethod
    async def get_by_id(self, id: str) -> dict[str, Any] | None:
        """Get value by id."""

    @abstractmethod
    async def get_by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        """Get values by ids."""

    @abstractmethod
    async def filter_keys(self, keys: set[str]) -> set[str]:
        """Return keys that do NOT exist in storage (for deduplication)."""

    @abstractmethod
    async def upsert(self, data: dict[str, dict[str, Any]]) -> None:
        """Upsert data."""

    @abstractmethod
    async def delete(self, ids: list[str]) -> None:
        """Delete specific records by ID."""

    @abstractmethod
    async def is_empty(self) -> bool:
        """Check if storage is empty."""


@dataclass
class BaseGraphStorage(StorageNameSpace, ABC):
    """All edge operations are treated as undirected."""

    embedding_func: Any  # EmbeddingFunc

    @abstractmethod
    async def has_node(self, node_id: str) -> bool: ...

    @abstractmethod
    async def has_edge(self, source_node_id: str, target_node_id: str) -> bool: ...

    @abstractmethod
    async def node_degree(self, node_id: str) -> int: ...

    @abstractmethod
    async def edge_degree(self, src_id: str, tgt_id: str) -> int: ...

    @abstractmethod
    async def get_node(self, node_id: str) -> dict[str, str] | None: ...

    @abstractmethod
    async def get_edge(
        self, source_node_id: str, target_node_id: str
    ) -> dict[str, str] | None: ...

    @abstractmethod
    async def get_node_edges(
        self, source_node_id: str
    ) -> list[tuple[str, str]] | None: ...

    # Default batch implementations (override in backends that support batching)
    async def get_nodes_batch(self, node_ids: list[str]) -> dict[str, dict]:
        result = {}
        for node_id in node_ids:
            node = await self.get_node(node_id)
            if node is not None:
                result[node_id] = node
        return result

    async def node_degrees_batch(self, node_ids: list[str]) -> dict[str, int]:
        result = {}
        for node_id in node_ids:
            result[node_id] = await self.node_degree(node_id)
        return result

    async def edge_degrees_batch(
        self, edge_pairs: list[tuple[str, str]]
    ) -> dict[tuple[str, str], int]:
        result = {}
        for src_id, tgt_id in edge_pairs:
            result[(src_id, tgt_id)] = await self.edge_degree(src_id, tgt_id)
        return result

    async def get_edges_batch(
        self, pairs: list[dict[str, str]]
    ) -> dict[tuple[str, str], dict]:
        result = {}
        for pair in pairs:
            src_id, tgt_id = pair["src"], pair["tgt"]
            edge = await self.get_edge(src_id, tgt_id)
            if edge is not None:
                result[(src_id, tgt_id)] = edge
        return result

    async def get_nodes_edges_batch(
        self, node_ids: list[str]
    ) -> dict[str, list[tuple[str, str]]]:
        result = {}
        for node_id in node_ids:
            edges = await self.get_node_edges(node_id)
            result[node_id] = edges if edges is not None else []
        return result

    @abstractmethod
    async def upsert_node(self, node_id: str, node_data: dict[str, str]) -> None: ...

    @abstractmethod
    async def upsert_edge(
        self, source_node_id: str, target_node_id: str, edge_data: dict[str, str]
    ) -> None: ...

    @abstractmethod
    async def delete_node(self, node_id: str) -> None: ...

    @abstractmethod
    async def remove_nodes(self, nodes: list[str]) -> None: ...

    @abstractmethod
    async def remove_edges(self, edges: list[tuple[str, str]]) -> None: ...

    @abstractmethod
    async def get_all_labels(self) -> list[str]: ...

    @abstractmethod
    async def get_knowledge_graph(
        self, node_label: str, max_depth: int = 3, max_nodes: int = 1000
    ) -> KnowledgeGraph: ...

    @abstractmethod
    async def get_all_nodes(self) -> list[dict]: ...

    @abstractmethod
    async def get_all_edges(self) -> list[dict]: ...

    @abstractmethod
    async def get_popular_labels(self, limit: int = 300) -> list[str]: ...

    @abstractmethod
    async def search_labels(self, query: str, limit: int = 50) -> list[str]: ...

    async def get_neighbors_with_scores(
        self,
        entity_ids: list[str],
        max_hops: int = 2,
        max_results: int = 50,
        exclude_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """BFS from seed entity_ids up to max_hops hops.
        Returns dicts with: entity_id, entity_type, description, source_id,
        file_path, hop_distance, best_score.
        This default implementation is a fallback for non-Neo4j backends;
        Neo4jGraphStorage overrides it with a single efficient Cypher query.
        """
        if not entity_ids:
            return []
        exclude = exclude_ids or set(entity_ids)
        visited: set[str] = set(entity_ids)
        frontier: list[str] = list(entity_ids)
        results: list[dict[str, Any]] = []
        for hop in range(1, max_hops + 1):
            next_frontier: list[str] = []
            for seed in frontier:
                edges = await self.get_node_edges(seed)
                if not edges:
                    continue
                for src, tgt in edges:
                    neighbor = tgt if src == seed else src
                    if neighbor not in visited and neighbor not in exclude:
                        visited.add(neighbor)
                        next_frontier.append(neighbor)
                        node = await self.get_node(neighbor)
                        if node:
                            results.append({
                                "entity_id": neighbor,
                                "entity_type": node.get("entity_type", "UNKNOWN"),
                                "description": node.get("description", ""),
                                "source_id": node.get("source_id", ""),
                                "file_path": node.get("file_path", ""),
                                "hop_distance": hop,
                                "best_score": 1.0 / hop,
                            })
                        if len(results) >= max_results:
                            return results
            frontier = next_frontier
            if not frontier:
                break
        return results[:max_results]


# ---------------------------------------------------------------------------
# Document processing status
# ---------------------------------------------------------------------------

class DocStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PREPROCESSED = "preprocessed"
    PROCESSED = "processed"
    FAILED = "failed"


@dataclass
class DocProcessingStatus:
    content_summary: str
    content_length: int
    file_path: str
    status: DocStatus
    created_at: str
    updated_at: str
    track_id: str | None = None
    chunks_count: int | None = None
    chunks_list: list[str] | None = field(default_factory=list)
    error_msg: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.chunks_list is None:
            self.chunks_list = []


@dataclass
class DocStatusStorage(BaseKVStorage, ABC):
    """Base class for document status storage."""

    @abstractmethod
    async def get_status_counts(self) -> dict[str, int]: ...

    @abstractmethod
    async def get_docs_by_status(
        self, status: DocStatus
    ) -> dict[str, DocProcessingStatus]: ...

    @abstractmethod
    async def get_docs_by_statuses(
        self, statuses: list[DocStatus]
    ) -> dict[str, DocProcessingStatus]: ...

    @abstractmethod
    async def get_doc_by_file_path(self, file_path: str) -> dict[str, Any] | None: ...


# ---------------------------------------------------------------------------
# Query results
# ---------------------------------------------------------------------------

class StoragesStatus(str, Enum):
    NOT_CREATED = "not_created"
    CREATED = "created"
    INITIALIZED = "initialized"
    FINALIZED = "finalized"


@dataclass
class DeletionResult:
    status: Literal["success", "not_found", "not_allowed", "fail"]
    doc_id: str
    message: str
    status_code: int = 200
    file_path: str | None = None


@dataclass
class QueryResult:
    content: Optional[str] = None
    response_iterator: Optional[AsyncIterator[str]] = None
    raw_data: Optional[Dict[str, Any]] = None
    is_streaming: bool = False

    @property
    def reference_list(self) -> List[Dict[str, str]]:
        if self.raw_data:
            return self.raw_data.get("data", {}).get("references", [])
        return []

    @property
    def metadata(self) -> Dict[str, Any]:
        if self.raw_data:
            return self.raw_data.get("metadata", {})
        return {}
