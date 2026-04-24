from __future__ import annotations

from pydantic import BaseModel
from typing import Any, Optional


class GPTKeywordExtractionFormat(BaseModel):
    high_level_keywords: list[str]
    low_level_keywords: list[str]


class KnowledgeGraphNode(BaseModel):
    id: str
    labels: list[str]
    properties: dict[str, Any]


class KnowledgeGraphEdge(BaseModel):
    id: str
    type: Optional[str]
    source: str
    target: str
    properties: dict[str, Any]


class KnowledgeGraph(BaseModel):
    nodes: list[KnowledgeGraphNode] = []
    edges: list[KnowledgeGraphEdge] = []
    is_truncated: bool = False
