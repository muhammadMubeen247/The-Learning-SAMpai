"""
Neo4j graph storage adapter implementing BaseGraphStorage.
Ported from LightRAG/lightrag/kg/neo4j_impl.py with:
  - LightRAG imports replaced with app.rag.*
  - pipmaster removed (neo4j installed via requirements.txt)
  - Simplified workspace isolation via node labels
  - shared_storage replaced with a simple asyncio.Lock
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.rag.base import BaseGraphStorage
from app.rag.types import KnowledgeGraph, KnowledgeGraphEdge, KnowledgeGraphNode
from app.rag.utils import logger

try:
    from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncManagedTransaction
    from neo4j import exceptions as neo4jExceptions
except ImportError as e:
    raise ImportError(
        "neo4j driver not installed. Add 'neo4j' to requirements.txt."
    ) from e

import logging
logging.getLogger("neo4j").setLevel(logging.ERROR)

# Retry configuration for transient errors
_READ_RETRY_EXCEPTIONS = (
    neo4jExceptions.ServiceUnavailable,
    neo4jExceptions.TransientError,
    neo4jExceptions.SessionExpired,
    ConnectionResetError,
    OSError,
)
_WRITE_RETRY_EXCEPTIONS = (
    neo4jExceptions.ServiceUnavailable,
    neo4jExceptions.TransientError,
    neo4jExceptions.WriteServiceUnavailable,
    neo4jExceptions.ClientError,
    neo4jExceptions.SessionExpired,
    ConnectionResetError,
    OSError,
)

READ_RETRY = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(_READ_RETRY_EXCEPTIONS),
    reraise=True,
    before_sleep=lambda rs: logger.warning(
        "Neo4j READ retry #%d after: %s", rs.attempt_number, rs.outcome.exception()
    ),
)
WRITE_RETRY = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(_WRITE_RETRY_EXCEPTIONS),
    reraise=True,
    before_sleep=lambda rs: logger.warning(
        "Neo4j WRITE retry #%d after: %s", rs.attempt_number, rs.outcome.exception()
    ),
)

# Module-level init lock (replaces LightRAG's shared_storage lock)
import asyncio
_init_lock = asyncio.Lock()


@dataclass
class Neo4jGraphStorage(BaseGraphStorage):
    """
    Graph storage using Neo4j.
    Each classroom workspace maps to a Neo4j node label for isolation.
    Workspace label = sanitized classroom_{id}.
    """

    embedding_func: Any = field(default=None)

    def __post_init__(self):
        self._driver: AsyncDriver | None = None
        self._DATABASE: str | None = None

    def _get_workspace_label(self) -> str:
        """Sanitized workspace label safe for Cypher backtick-quoted identifiers."""
        ws = self.workspace.strip() or "base"
        return ws.replace("`", "``")

    def _normalize_index_suffix(self, label: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9_]+", "_", label).strip("_") or "base"
        if not re.match(r"[A-Za-z_]", normalized[0]):
            normalized = f"ws_{normalized}"
        return normalized

    def _get_fulltext_index_name(self, label: str) -> str:
        return f"entity_id_fulltext_idx_{self._normalize_index_suffix(label)}"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self):
        async with _init_lock:
            uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
            username = os.environ.get("NEO4J_USERNAME", "neo4j")
            password = os.environ.get("NEO4J_PASSWORD", "password")
            max_pool = int(os.environ.get("NEO4J_MAX_CONNECTION_POOL_SIZE", "50"))

            self._driver = AsyncGraphDatabase.driver(
                uri,
                auth=(username, password),
                max_connection_pool_size=max_pool,
                connection_timeout=30.0,
            )

            database = os.environ.get("NEO4J_DATABASE", None)
            self._DATABASE = database

            # Verify connectivity and create indexes
            for db in (database, None):
                self._DATABASE = db
                try:
                    async with self._driver.session(database=db) as session:
                        result = await session.run("MATCH (n) RETURN n LIMIT 0")
                        await result.consume()
                        logger.info(f"[{self.workspace}] Connected to Neo4j at {uri} (db={db})")
                    # Create B-Tree index
                    workspace_label = self._get_workspace_label()
                    async with self._driver.session(database=db) as session:
                        result = await session.run(
                            f"CREATE INDEX IF NOT EXISTS FOR (n:`{workspace_label}`) ON (n.entity_id)"
                        )
                        await result.consume()
                    await self._create_fulltext_index(workspace_label)
                    break
                except neo4jExceptions.AuthError:
                    raise
                except neo4jExceptions.ClientError as e:
                    if e.code == "Neo.ClientError.Database.DatabaseNotFound" and db is not None:
                        logger.warning(f"[{self.workspace}] Database '{db}' not found, falling back to default.")
                        continue
                    raise
                except Exception as e:
                    if db is not None:
                        continue
                    raise

    async def _create_fulltext_index(self, workspace_label: str):
        index_name = self._get_fulltext_index_name(workspace_label)
        try:
            async with self._driver.session(database=self._DATABASE) as session:
                result = await session.run("SHOW FULLTEXT INDEXES")
                indexes = await result.data()
                await result.consume()
                existing = next((i for i in indexes if i["name"] == index_name), None)
                if existing and existing.get("state") == "ONLINE":
                    return
                try:
                    r = await session.run(
                        f"""CREATE FULLTEXT INDEX {index_name}
                        FOR (n:`{workspace_label}`) ON EACH [n.entity_id]
                        OPTIONS {{indexConfig: {{`fulltext.analyzer`: 'standard'}}}}"""
                    )
                    await r.consume()
                    logger.info(f"[{self.workspace}] Created fulltext index '{index_name}'")
                except Exception as e:
                    logger.warning(f"[{self.workspace}] Could not create fulltext index: {e}")
        except Exception as e:
            logger.warning(f"[{self.workspace}] Fulltext index setup failed: {e}")

    async def finalize(self):
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("[%s] Neo4j driver closed.", self.workspace)

    async def index_done_callback(self) -> None:
        pass  # Neo4j persists automatically

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    @READ_RETRY
    async def has_node(self, node_id: str) -> bool:
        wl = self._get_workspace_label()
        async with self._driver.session(database=self._DATABASE, default_access_mode="READ") as session:
            result = await session.run(
                f"MATCH (n:`{wl}` {{entity_id: $id}}) RETURN count(n) > 0 AS exists",
                id=node_id,
            )
            record = await result.single()
            await result.consume()
            return record["exists"] if record else False

    @READ_RETRY
    async def has_edge(self, source_node_id: str, target_node_id: str) -> bool:
        wl = self._get_workspace_label()
        async with self._driver.session(database=self._DATABASE, default_access_mode="READ") as session:
            result = await session.run(
                f"MATCH (a:`{wl}` {{entity_id: $src}})-[r]-(b:`{wl}` {{entity_id: $tgt}}) RETURN COUNT(r) > 0 AS exists",
                src=source_node_id, tgt=target_node_id,
            )
            record = await result.single()
            await result.consume()
            return record["exists"] if record else False

    @READ_RETRY
    async def node_degree(self, node_id: str) -> int:
        wl = self._get_workspace_label()
        async with self._driver.session(database=self._DATABASE, default_access_mode="READ") as session:
            result = await session.run(
                f"MATCH (n:`{wl}` {{entity_id: $id}}) OPTIONAL MATCH (n)-[r]-() RETURN COUNT(r) AS degree",
                id=node_id,
            )
            record = await result.single()
            await result.consume()
            return record["degree"] if record else 0

    @READ_RETRY
    async def node_degrees_batch(self, node_ids: list[str]) -> dict[str, int]:
        wl = self._get_workspace_label()
        async with self._driver.session(database=self._DATABASE, default_access_mode="READ") as session:
            result = await session.run(
                f"""UNWIND $ids AS id
                MATCH (n:`{wl}` {{entity_id: id}})
                RETURN n.entity_id AS entity_id, count {{ (n)--() }} AS degree""",
                ids=node_ids,
            )
            degrees = {}
            async for record in result:
                degrees[record["entity_id"]] = record["degree"]
            await result.consume()
            for nid in node_ids:
                degrees.setdefault(nid, 0)
            return degrees

    async def edge_degree(self, src_id: str, tgt_id: str) -> int:
        src = await self.node_degree(src_id)
        tgt = await self.node_degree(tgt_id)
        return int(src or 0) + int(tgt or 0)

    async def edge_degrees_batch(self, edge_pairs: list[tuple[str, str]]) -> dict[tuple[str, str], int]:
        unique_ids = list({n for pair in edge_pairs for n in pair})
        degrees = await self.node_degrees_batch(unique_ids)
        return {(s, t): degrees.get(s, 0) + degrees.get(t, 0) for s, t in edge_pairs}

    @READ_RETRY
    async def get_node(self, node_id: str) -> dict[str, str] | None:
        wl = self._get_workspace_label()
        async with self._driver.session(database=self._DATABASE, default_access_mode="READ") as session:
            result = await session.run(
                f"MATCH (n:`{wl}` {{entity_id: $id}}) RETURN n",
                id=node_id,
            )
            records = await result.fetch(2)
            await result.consume()
            if not records:
                return None
            node_dict = dict(records[0]["n"])
            node_dict.pop("labels", None)
            return node_dict

    @READ_RETRY
    async def get_nodes_batch(self, node_ids: list[str]) -> dict[str, dict]:
        import time as _time
        _t0 = _time.time()
        wl = self._get_workspace_label()
        async with self._driver.session(database=self._DATABASE, default_access_mode="READ") as session:
            result = await session.run(
                f"""UNWIND $ids AS id
                MATCH (n:`{wl}` {{entity_id: id}})
                RETURN n.entity_id AS entity_id, n""",
                ids=node_ids,
            )
            nodes = {}
            async for record in result:
                nd = dict(record["n"])
                nd.pop("labels", None)
                nodes[record["entity_id"]] = nd
            await result.consume()
        logger.debug(
            "[%s] get_nodes_batch(%d ids) returned %d in %.3fs",
            self.workspace, len(node_ids), len(nodes), _time.time() - _t0,
        )
        return nodes

    @READ_RETRY
    async def get_edge(self, source_node_id: str, target_node_id: str) -> dict[str, str] | None:
        wl = self._get_workspace_label()
        async with self._driver.session(database=self._DATABASE, default_access_mode="READ") as session:
            result = await session.run(
                f"""MATCH (a:`{wl}` {{entity_id: $src}})-[r]-(b:`{wl}` {{entity_id: $tgt}})
                RETURN properties(r) AS props""",
                src=source_node_id, tgt=target_node_id,
            )
            records = await result.fetch(2)
            await result.consume()
            if not records:
                return None
            props = dict(records[0]["props"])
            props.setdefault("weight", 1.0)
            props.setdefault("source_id", None)
            props.setdefault("description", None)
            props.setdefault("keywords", None)
            return props

    @READ_RETRY
    async def get_edges_batch(self, pairs: list[dict[str, str]]) -> dict[tuple[str, str], dict]:
        import time as _time
        _t0 = _time.time()
        wl = self._get_workspace_label()
        async with self._driver.session(database=self._DATABASE, default_access_mode="READ") as session:
            result = await session.run(
                f"""UNWIND $pairs AS pair
                MATCH (a:`{wl}` {{entity_id: pair.src}})-[r]-(b:`{wl}` {{entity_id: pair.tgt}})
                RETURN pair.src AS src_id, pair.tgt AS tgt_id, collect(properties(r)) AS edges""",
                pairs=pairs,
            )
            out = {}
            async for record in result:
                src, tgt = record["src_id"], record["tgt_id"]
                edges = record["edges"]
                if edges:
                    props = dict(edges[0])
                    props.setdefault("weight", 1.0)
                    out[(src, tgt)] = props
                else:
                    out[(src, tgt)] = {"weight": 1.0, "source_id": None, "description": None, "keywords": None}
            await result.consume()
        logger.debug(
            "[%s] get_edges_batch(%d pairs) returned %d in %.3fs",
            self.workspace, len(pairs), len(out), _time.time() - _t0,
        )
        return out

    @READ_RETRY
    async def get_node_edges(self, source_node_id: str) -> list[tuple[str, str]] | None:
        wl = self._get_workspace_label()
        async with self._driver.session(database=self._DATABASE, default_access_mode="READ") as session:
            result = await session.run(
                f"""MATCH (n:`{wl}` {{entity_id: $id}})
                OPTIONAL MATCH (n)-[r]-(m:`{wl}`)
                WHERE m.entity_id IS NOT NULL
                RETURN n.entity_id AS src, m.entity_id AS tgt""",
                id=source_node_id,
            )
            edges = []
            async for record in result:
                src, tgt = record["src"], record["tgt"]
                if src and tgt:
                    edges.append((src, tgt))
            await result.consume()
            return edges

    @READ_RETRY
    async def get_nodes_edges_batch(self, node_ids: list[str]) -> dict[str, list[tuple[str, str]]]:
        wl = self._get_workspace_label()
        async with self._driver.session(database=self._DATABASE, default_access_mode="READ") as session:
            result = await session.run(
                f"""UNWIND $ids AS id
                MATCH (n:`{wl}` {{entity_id: id}})
                OPTIONAL MATCH (n)-[r]-(m:`{wl}`)
                RETURN id AS queried_id, n.entity_id AS node_id, m.entity_id AS connected_id,
                       startNode(r).entity_id AS start_id""",
                ids=node_ids,
            )
            out = {nid: [] for nid in node_ids}
            async for record in result:
                qid = record["queried_id"]
                nid = record["node_id"]
                cid = record["connected_id"]
                if nid and cid:
                    out[qid].append((nid, cid))
            await result.consume()
            return out

    @READ_RETRY
    async def get_neighbors_with_scores(
        self,
        entity_ids: list[str],
        max_hops: int = 2,
        max_results: int = 50,
        exclude_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Single-query BFS from multiple seed entities using weighted path scoring.
        Score = product(edge_weights) / hop_count, best path per neighbor.
        """
        if not entity_ids:
            return []
        import time as _time
        _t0 = _time.time()
        wl = self._get_workspace_label()
        exclude = list(exclude_ids) if exclude_ids else list(entity_ids)

        # max_hops interpolated as f-string — Cypher disallows params for
        # variable-length path bounds. wl is safe (backtick-escaped by _get_workspace_label).
        cypher = f"""
            MATCH (seed:`{wl}`)-[r*1..{max_hops}]-(neighbor:`{wl}`)
            WHERE seed.entity_id IN $seed_ids
              AND neighbor.entity_id IS NOT NULL
              AND NOT neighbor.entity_id IN $exclude_ids
            WITH neighbor,
                 size(r) AS hops,
                 reduce(w = 1.0, rel IN r |
                     w * coalesce(toFloat(rel.weight), 1.0)
                 ) AS path_weight
            WITH neighbor,
                 min(hops) AS hop_distance,
                 max(path_weight / hops) AS best_score
            ORDER BY best_score DESC
            LIMIT $max_results
            RETURN
                neighbor.entity_id   AS entity_id,
                neighbor.entity_type AS entity_type,
                neighbor.description AS description,
                neighbor.source_id   AS source_id,
                neighbor.file_path   AS file_path,
                hop_distance,
                best_score
        """
        async with self._driver.session(
            database=self._DATABASE, default_access_mode="READ"
        ) as session:
            result = await session.run(
                cypher,
                seed_ids=list(entity_ids),
                exclude_ids=exclude,
                max_results=max_results,
            )
            rows: list[dict[str, Any]] = []
            async for record in result:
                rows.append({
                    "entity_id":    record["entity_id"],
                    "entity_type":  record["entity_type"] or "UNKNOWN",
                    "description":  record["description"] or "",
                    "source_id":    record["source_id"] or "",
                    "file_path":    record["file_path"] or "",
                    "hop_distance": int(record["hop_distance"]),
                    "best_score":   float(record["best_score"]),
                })
            await result.consume()
        logger.debug(
            "[%s] get_neighbors_with_scores(%d seeds, hops=%d) → %d neighbors in %.3fs",
            self.workspace, len(entity_ids), max_hops, len(rows), _time.time() - _t0,
        )
        return rows

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    @WRITE_RETRY
    async def upsert_node(self, node_id: str, node_data: dict[str, str]) -> None:
        wl = self._get_workspace_label()
        entity_type = node_data.get("entity_type", "UNKNOWN")
        if not isinstance(entity_type, str):
            entity_type = str(entity_type)
        entity_type = entity_type.replace("`", "").split(",")[0].strip() or "UNKNOWN"

        # Backtick-escape entity_type label so spaces/special chars are safe
        safe_entity_type = entity_type.replace("`", "``")

        props = dict(node_data)
        props["entity_type"] = entity_type
        if "entity_id" not in props:
            props["entity_id"] = node_id

        async with self._driver.session(database=self._DATABASE) as session:
            async def _exec(tx: AsyncManagedTransaction):
                r = await tx.run(
                    f"""MERGE (n:`{wl}` {{entity_id: $eid}})
                    SET n += $props
                    SET n:`{safe_entity_type}`""",
                    eid=node_id, props=props,
                )
                await r.consume()
            await session.execute_write(_exec)

    @WRITE_RETRY
    async def upsert_edge(
        self, source_node_id: str, target_node_id: str, edge_data: dict[str, str]
    ) -> None:
        wl = self._get_workspace_label()
        async with self._driver.session(database=self._DATABASE) as session:
            async def _exec(tx: AsyncManagedTransaction):
                r = await tx.run(
                    f"""MATCH (src:`{wl}` {{entity_id: $src}})
                    MATCH (tgt:`{wl}` {{entity_id: $tgt}})
                    MERGE (src)-[r:RELATED]->(tgt)
                    SET r += $props""",
                    src=source_node_id, tgt=target_node_id, props=edge_data,
                )
                await r.consume()
            await session.execute_write(_exec)

    @WRITE_RETRY
    async def delete_node(self, node_id: str) -> None:
        wl = self._get_workspace_label()
        async with self._driver.session(database=self._DATABASE) as session:
            async def _exec(tx: AsyncManagedTransaction):
                r = await tx.run(
                    f"MATCH (n:`{wl}` {{entity_id: $id}}) DETACH DELETE n",
                    id=node_id,
                )
                await r.consume()
            await session.execute_write(_exec)

    async def remove_nodes(self, nodes: list[str]) -> None:
        for node_id in nodes:
            await self.delete_node(node_id)

    async def remove_edges(self, edges: list[tuple[str, str]]) -> None:
        wl = self._get_workspace_label()
        async with self._driver.session(database=self._DATABASE) as session:
            for src, tgt in edges:
                async def _exec(tx: AsyncManagedTransaction, s=src, t=tgt):
                    r = await tx.run(
                        f"MATCH (a:`{wl}` {{entity_id: $s}})-[r]-(b:`{wl}` {{entity_id: $t}}) DELETE r",
                        s=s, t=t,
                    )
                    await r.consume()
                await session.execute_write(_exec)

    # ------------------------------------------------------------------
    # Label / search operations
    # ------------------------------------------------------------------

    async def get_all_labels(self) -> list[str]:
        wl = self._get_workspace_label()
        async with self._driver.session(database=self._DATABASE, default_access_mode="READ") as session:
            result = await session.run(
                f"MATCH (n:`{wl}`) WHERE n.entity_id IS NOT NULL RETURN n.entity_id AS label ORDER BY label"
            )
            labels = []
            async for record in result:
                labels.append(record["label"])
            await result.consume()
            return labels

    async def get_popular_labels(self, limit: int = 300) -> list[str]:
        wl = self._get_workspace_label()
        async with self._driver.session(database=self._DATABASE, default_access_mode="READ") as session:
            result = await session.run(
                f"""MATCH (n:`{wl}`)
                OPTIONAL MATCH (n)-[r]-()
                WITH n.entity_id AS label, COUNT(r) AS degree
                WHERE label IS NOT NULL
                ORDER BY degree DESC
                LIMIT $limit
                RETURN label""",
                limit=limit,
            )
            labels = []
            async for record in result:
                labels.append(record["label"])
            await result.consume()
            return labels

    async def search_labels(self, query: str, limit: int = 50) -> list[str]:
        wl = self._get_workspace_label()
        async with self._driver.session(database=self._DATABASE, default_access_mode="READ") as session:
            result = await session.run(
                f"""MATCH (n:`{wl}`)
                WHERE n.entity_id CONTAINS $q
                RETURN n.entity_id AS label
                LIMIT $limit""",
                q=query, limit=limit,
            )
            labels = []
            async for record in result:
                labels.append(record["label"])
            await result.consume()
            return labels

    # ------------------------------------------------------------------
    # Bulk retrieval for graph visualization
    # ------------------------------------------------------------------

    async def get_all_nodes(self) -> list[dict]:
        wl = self._get_workspace_label()
        async with self._driver.session(database=self._DATABASE, default_access_mode="READ") as session:
            result = await session.run(f"MATCH (n:`{wl}`) RETURN properties(n) AS props")
            nodes = []
            async for record in result:
                nodes.append(dict(record["props"]))
            await result.consume()
            return nodes

    async def get_all_edges(self) -> list[dict]:
        wl = self._get_workspace_label()
        async with self._driver.session(database=self._DATABASE, default_access_mode="READ") as session:
            result = await session.run(
                f"""MATCH (a:`{wl}`)-[r]-(b:`{wl}`)
                WHERE id(a) < id(b)
                RETURN a.entity_id AS src, b.entity_id AS tgt, properties(r) AS props"""
            )
            edges = []
            async for record in result:
                e = dict(record["props"])
                e["src_id"] = record["src"]
                e["tgt_id"] = record["tgt"]
                edges.append(e)
            await result.consume()
            return edges

    # ------------------------------------------------------------------
    # Knowledge graph subgraph retrieval
    # ------------------------------------------------------------------

    async def get_knowledge_graph(
        self, node_label: str, max_depth: int = 3, max_nodes: int = 1000
    ) -> KnowledgeGraph:
        wl = self._get_workspace_label()
        max_nodes = min(max_nodes, self.global_config.get("max_graph_nodes", 1000))
        kg = KnowledgeGraph()

        async with self._driver.session(database=self._DATABASE, default_access_mode="READ") as session:
            if node_label == "*":
                # All nodes (up to max_nodes, sorted by degree)
                count_result = await session.run(f"MATCH (n:`{wl}`) RETURN count(n) AS total")
                count_record = await count_result.single()
                await count_result.consume()
                if count_record and count_record["total"] > max_nodes:
                    kg.is_truncated = True

                result = await session.run(
                    f"""MATCH (n:`{wl}`)
                    OPTIONAL MATCH (n)-[r]-()
                    WITH n, COUNT(r) AS degree ORDER BY degree DESC LIMIT $limit
                    RETURN n""",
                    limit=max_nodes,
                )
                seen_node_ids = set()
                async for record in result:
                    node = dict(record["n"])
                    eid = node.get("entity_id", "")
                    if eid and eid not in seen_node_ids:
                        seen_node_ids.add(eid)
                        kg.nodes.append(KnowledgeGraphNode(
                            id=eid,
                            labels=[node.get("entity_type", "")],
                            properties=node,
                        ))
                await result.consume()

                # Get edges between those nodes
                node_ids = [n.id for n in kg.nodes]
                if node_ids:
                    edge_result = await session.run(
                        f"""MATCH (a:`{wl}`)-[r]-(b:`{wl}`)
                        WHERE a.entity_id IN $ids AND b.entity_id IN $ids AND id(a) < id(b)
                        RETURN a.entity_id AS src, b.entity_id AS tgt, properties(r) AS props, type(r) AS rtype""",
                        ids=node_ids,
                    )
                    async for record in edge_result:
                        props = dict(record["props"])
                        kg.edges.append(KnowledgeGraphEdge(
                            id=f"{record['src']}-{record['tgt']}",
                            type=record["rtype"],
                            source=record["src"],
                            target=record["tgt"],
                            properties=props,
                        ))
                    await edge_result.consume()
            else:
                # BFS from start node
                result = await session.run(
                    f"""MATCH path = (start:`{wl}` {{entity_id: $eid}})-[*1..{max_depth}]-(connected:`{wl}`)
                    WITH nodes(path) AS path_nodes, relationships(path) AS path_rels
                    UNWIND path_nodes AS n
                    WITH DISTINCT n, path_rels
                    RETURN n, path_rels
                    LIMIT $limit""",
                    eid=node_label, limit=max_nodes,
                )
                seen_nodes = set()
                seen_edges = set()
                async for record in result:
                    node = dict(record["n"])
                    eid = node.get("entity_id", "")
                    if eid and eid not in seen_nodes:
                        seen_nodes.add(eid)
                        kg.nodes.append(KnowledgeGraphNode(
                            id=eid,
                            labels=[node.get("entity_type", "")],
                            properties=node,
                        ))
                await result.consume()
                if len(kg.nodes) >= max_nodes:
                    kg.is_truncated = True

        return kg

    # ------------------------------------------------------------------
    # Drop all data for this workspace
    # ------------------------------------------------------------------

    async def drop(self) -> dict[str, str]:
        wl = self._get_workspace_label()
        try:
            async with self._driver.session(database=self._DATABASE) as session:
                async def _exec(tx: AsyncManagedTransaction):
                    r = await tx.run(f"MATCH (n:`{wl}`) DETACH DELETE n")
                    await r.consume()
                await session.execute_write(_exec)
            return {"status": "success", "message": "data dropped"}
        except Exception as e:
            logger.error(f"Neo4jGraphStorage drop error: {e}")
            return {"status": "error", "message": str(e)}
