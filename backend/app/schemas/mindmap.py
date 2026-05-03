"""
Mindmap Pydantic schemas for routes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

class MindmapStatusOut(str):
    pass


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class GenerateMindmapRequest(BaseModel):
    force: bool = False


class AskInThreadRequest(BaseModel):
    content: str
    active_node_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Response shapes
# ---------------------------------------------------------------------------

class MindmapOut(BaseModel):
    id: int
    file_id: int
    classroom_id: int
    status: str
    root_topic: Optional[str] = None
    root_description: Optional[str] = None
    tree_data: Optional[Any] = None
    node_count: int
    generation_meta: Optional[Any] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ExploreNodeResponse(BaseModel):
    already_explored: bool
    last_message_id: Optional[int] = None
    marker_id: Optional[int] = None
    placeholder_id: Optional[int] = None


class ChatMessageOut(BaseModel):
    id: int
    mindmap_id: int
    user_id: int
    node_id: Optional[str] = None
    role: str
    content: str
    message_metadata: Any
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessageOut]
    has_more: bool


class AskResponse(BaseModel):
    message: ChatMessageOut
