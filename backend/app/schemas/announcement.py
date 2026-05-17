from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, model_validator


class CommentCreate(BaseModel):
    content: str


class CommentOut(BaseModel):
    id: int
    announcement_id: int
    created_by_id: int
    created_by_username: str
    content: str
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _flatten(cls, data: object) -> object:
        if hasattr(data, "__dict__"):
            return {
                "id": data.id,
                "announcement_id": data.announcement_id,
                "created_by_id": data.created_by_id,
                "created_by_username": data.created_by.username if data.created_by else "",
                "content": data.content,
                "created_at": data.created_at,
            }
        return data


class AnnouncementCreate(BaseModel):
    content: str


class AnnouncementOut(BaseModel):
    id: int
    classroom_id: int
    created_by_id: int
    created_by_username: str
    content: str
    created_at: datetime
    updated_at: datetime
    comments: list[CommentOut]

    @model_validator(mode="before")
    @classmethod
    def _flatten(cls, data: object) -> object:
        if hasattr(data, "__dict__"):
            return {
                "id": data.id,
                "classroom_id": data.classroom_id,
                "created_by_id": data.created_by_id,
                "created_by_username": data.created_by.username if data.created_by else "",
                "content": data.content,
                "created_at": data.created_at,
                "updated_at": data.updated_at,
                "comments": data.comments,
            }
        return data
