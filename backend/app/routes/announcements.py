"""
Announcement routes — create, list, delete announcements and their comments.
Announcements are scoped to a classroom. Only the classroom owner can post;
all members can read and comment.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.classroom import Classroom, classroom_members
from app.models.announcement import Announcement, AnnouncementComment
from app.schemas.announcement import (
    AnnouncementCreate,
    AnnouncementOut,
    CommentCreate,
    CommentOut,
)

router = APIRouter(prefix="/announcements", tags=["Announcements"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _load_announcement(
    announcement_id: int,
    db: AsyncSession,
) -> Announcement:
    result = await db.execute(
        select(Announcement)
        .options(
            selectinload(Announcement.created_by),
            selectinload(Announcement.comments).selectinload(AnnouncementComment.created_by),
        )
        .where(Announcement.id == announcement_id)
    )
    ann = result.scalar_one_or_none()
    if ann is None:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return ann


async def _assert_classroom_member(
    db: AsyncSession, classroom_id: int, user_id: int
) -> Classroom:
    result = await db.execute(
        select(Classroom).where(Classroom.id == classroom_id)
    )
    classroom = result.scalar_one_or_none()
    if classroom is None:
        raise HTTPException(status_code=404, detail="Classroom not found")

    is_member = await db.scalar(
        select(
            select(classroom_members)
            .where(
                classroom_members.c.classroom_id == classroom_id,
                classroom_members.c.user_id == user_id,
            )
            .exists()
        )
    )
    if not is_member:
        raise HTTPException(status_code=403, detail="Not a member of this classroom")
    return classroom


# ---------------------------------------------------------------------------
# GET /announcements/classrooms/{classroom_id}
# ---------------------------------------------------------------------------

@router.get("/classrooms/{classroom_id}", response_model=list[AnnouncementOut])
async def list_announcements(
    classroom_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _assert_classroom_member(db, classroom_id, current_user.id)

    result = await db.execute(
        select(Announcement)
        .options(
            selectinload(Announcement.created_by),
            selectinload(Announcement.comments).selectinload(AnnouncementComment.created_by),
        )
        .where(Announcement.classroom_id == classroom_id)
        .order_by(Announcement.created_at.desc())
    )
    announcements = result.scalars().all()
    return [AnnouncementOut.model_validate(a) for a in announcements]


# ---------------------------------------------------------------------------
# POST /announcements/classrooms/{classroom_id}
# ---------------------------------------------------------------------------

@router.post("/classrooms/{classroom_id}", response_model=AnnouncementOut, status_code=201)
async def create_announcement(
    classroom_id: int,
    body: AnnouncementCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    classroom = await _assert_classroom_member(db, classroom_id, current_user.id)

    if classroom.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the classroom owner can post announcements")

    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Announcement content cannot be empty")

    ann = Announcement(
        classroom_id=classroom_id,
        created_by_id=current_user.id,
        content=content,
    )
    db.add(ann)
    await db.commit()

    return AnnouncementOut.model_validate(await _load_announcement(ann.id, db))


# ---------------------------------------------------------------------------
# DELETE /announcements/{announcement_id}
# ---------------------------------------------------------------------------

@router.delete("/announcements/{announcement_id}", status_code=204)
async def delete_announcement(
    announcement_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    ann = await _load_announcement(announcement_id, db)

    # Only the classroom owner can delete announcements
    result = await db.execute(
        select(Classroom).where(Classroom.id == ann.classroom_id)
    )
    classroom = result.scalar_one_or_none()
    if classroom is None or classroom.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the classroom owner can delete announcements")

    await db.delete(ann)
    await db.commit()


# ---------------------------------------------------------------------------
# POST /announcements/{announcement_id}/comments
# ---------------------------------------------------------------------------

@router.post("/announcements/{announcement_id}/comments", response_model=CommentOut, status_code=201)
async def add_comment(
    announcement_id: int,
    body: CommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    ann = await _load_announcement(announcement_id, db)
    await _assert_classroom_member(db, ann.classroom_id, current_user.id)

    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Comment cannot be empty")

    comment = AnnouncementComment(
        announcement_id=announcement_id,
        created_by_id=current_user.id,
        content=content,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    # Reload with relationship
    result = await db.execute(
        select(AnnouncementComment)
        .options(selectinload(AnnouncementComment.created_by))
        .where(AnnouncementComment.id == comment.id)
    )
    comment = result.scalar_one()
    return CommentOut.model_validate(comment)


# ---------------------------------------------------------------------------
# DELETE /announcements/{announcement_id}/comments/{comment_id}
# ---------------------------------------------------------------------------

@router.delete("/announcements/{announcement_id}/comments/{comment_id}", status_code=204)
async def delete_comment(
    announcement_id: int,
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(AnnouncementComment)
        .options(selectinload(AnnouncementComment.created_by))
        .where(
            AnnouncementComment.id == comment_id,
            AnnouncementComment.announcement_id == announcement_id,
        )
    )
    comment = result.scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")

    # Load announcement to check classroom ownership
    ann = await _load_announcement(announcement_id, db)
    classroom_result = await db.execute(
        select(Classroom).where(Classroom.id == ann.classroom_id)
    )
    classroom = classroom_result.scalar_one_or_none()

    # Allow comment author or classroom owner to delete
    is_owner = classroom and classroom.owner_id == current_user.id
    if comment.created_by_id != current_user.id and not is_owner:
        raise HTTPException(status_code=403, detail="Cannot delete another member's comment")

    await db.delete(comment)
    await db.commit()
