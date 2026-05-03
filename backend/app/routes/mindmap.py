"""
Mindmap routes.

Endpoints
---------
POST  /mindmap/files/{file_id}/generate          — create / start generation
GET   /mindmap/files/{file_id}                   — poll status / fetch tree
DELETE /mindmap/files/{file_id}                  — delete mindmap (owner only)

POST  /mindmap/{mindmap_id}/nodes/{node_id}/explore  — start node summary
GET   /mindmap/{mindmap_id}/chat                     — fetch chat history
POST  /mindmap/{mindmap_id}/chat/ask                 — conversational ask
DELETE /mindmap/{mindmap_id}/chat                    — clear chat history
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.classroom import Classroom, classroom_members
from app.models.file import File, ProcessingStatus
from app.models.folder import Folder
from app.models.mindmap import Mindmap, MindmapMessageRole, MindmapNodeChat, MindmapStatus
from app.schemas.mindmap import (
    AskInThreadRequest,
    AskResponse,
    ChatHistoryResponse,
    ChatMessageOut,
    ExploreNodeResponse,
    GenerateMindmapRequest,
    MindmapOut,
)
from app.services.mindmap_chat import (
    ask_in_thread,
    explore_node,
    generate_node_summary_task,
)
from app.services.mindmap_service import (
    _load_or_create_mindmap_row,
    generate_mindmap_task,
    get_mindmap_by_file,
)

router = APIRouter(prefix="/mindmap", tags=["Mindmap"])
logger = logging.getLogger("mindmap.routes")


# ---------------------------------------------------------------------------
# Access-control helper
# ---------------------------------------------------------------------------


async def _get_file_and_classroom(
    file_id: int, current_user, db: AsyncSession
) -> tuple[File, Classroom]:
    """Return (file, classroom) after verifying classroom membership."""
    file = await db.get(File, file_id)
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")

    result = await db.execute(select(Folder).where(Folder.id == file.folder_id))
    folder = result.scalar_one_or_none()
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")

    result = await db.execute(
        select(Classroom).where(Classroom.id == folder.classroom_id)
    )
    classroom = result.scalar_one_or_none()
    if classroom is None:
        raise HTTPException(status_code=404, detail="Classroom not found")

    is_member = await db.scalar(
        select(
            exists().where(
                (classroom_members.c.classroom_id == classroom.id)
                & (classroom_members.c.user_id == current_user.id)
            )
        )
    )
    if not is_member:
        raise HTTPException(
            status_code=403, detail="You are not a member of this classroom"
        )
    return file, classroom


async def _get_mindmap_and_classroom(
    mindmap_id: int, current_user, db: AsyncSession
) -> tuple[Mindmap, File, Classroom]:
    """Return (mindmap, file, classroom) after verifying membership."""
    mindmap = await db.get(Mindmap, mindmap_id)
    if mindmap is None:
        raise HTTPException(status_code=404, detail="Mindmap not found")

    file, classroom = await _get_file_and_classroom(
        mindmap.file_id, current_user, db
    )
    return mindmap, file, classroom


# ---------------------------------------------------------------------------
# Tree endpoints
# ---------------------------------------------------------------------------


@router.post("/files/{file_id}/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_mindmap(
    file_id: int,
    body: GenerateMindmapRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Trigger mindmap generation for a file.

    - If READY and force=False → return existing tree immediately.
    - If GENERATING → return in-flight record.
    - If PENDING/FAILED or force=True → (re)start generation.

    File must be in COMPLETED processing status.
    """
    file, classroom = await _get_file_and_classroom(file_id, current_user, db)

    if file.processing_status != ProcessingStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail="File is still processing. Wait until processing_status is COMPLETED.",
        )

    mindmap = await _load_or_create_mindmap_row(
        db, file_id, classroom.id, force=body.force
    )

    if mindmap.status == MindmapStatus.READY and not body.force:
        await db.commit()
        return {"detail": "already ready", "mindmap": MindmapOut.model_validate(mindmap)}

    if mindmap.status == MindmapStatus.GENERATING:
        await db.commit()
        return {"detail": "generating", "mindmap": MindmapOut.model_validate(mindmap)}

    await db.commit()

    background_tasks.add_task(
        generate_mindmap_task, file_id, classroom.id, body.force
    )

    return {"detail": "generation started", "mindmap": MindmapOut.model_validate(mindmap)}


@router.get("/files/{file_id}", response_model=MindmapOut)
async def get_mindmap(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Poll mindmap status and retrieve the tree once READY."""
    file, classroom = await _get_file_and_classroom(file_id, current_user, db)
    mindmap = await get_mindmap_by_file(db, file_id)
    if mindmap is None:
        raise HTTPException(status_code=404, detail="Mindmap not found")
    return mindmap


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mindmap(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete the mindmap tree (owner only). Does not delete chat history."""
    file, classroom = await _get_file_and_classroom(file_id, current_user, db)

    if classroom.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only the classroom owner can delete the mindmap."
        )

    mindmap = await get_mindmap_by_file(db, file_id)
    if mindmap is None:
        raise HTTPException(status_code=404, detail="Mindmap not found")

    await db.delete(mindmap)
    await db.commit()


# ---------------------------------------------------------------------------
# Per-node explore
# ---------------------------------------------------------------------------


@router.post(
    "/{mindmap_id}/nodes/{node_id}/explore",
    response_model=ExploreNodeResponse,
)
async def explore_node_endpoint(
    mindmap_id: int,
    node_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Mark a node as explored for this user.

    - Returns already_explored=True + last_message_id if summary exists.
    - Otherwise inserts MARKER + pending ASSISTANT, fires background summary task.
    """
    mindmap, file, classroom = await _get_mindmap_and_classroom(
        mindmap_id, current_user, db
    )

    if mindmap.status != MindmapStatus.READY:
        raise HTTPException(status_code=409, detail="Mindmap is not ready yet.")

    # Validate node_id exists in tree
    from app.services.mindmap_service import _find_node

    node = _find_node(mindmap.tree_data or {}, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found in mindmap.")

    result = await explore_node(db, mindmap_id, node_id, current_user.id)
    await db.commit()

    if not result.already_explored and result.placeholder_id is not None:
        background_tasks.add_task(
            generate_node_summary_task,
            mindmap_id,
            node_id,
            result.placeholder_id,
            file.id,
            classroom.id,
            current_user.id,
        )

    return result


# ---------------------------------------------------------------------------
# Chat endpoints
# ---------------------------------------------------------------------------


@router.get("/{mindmap_id}/chat", response_model=ChatHistoryResponse)
async def get_chat_history(
    mindmap_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    before_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Fetch per-user mindmap chat history in chronological order."""
    mindmap, file, classroom = await _get_mindmap_and_classroom(
        mindmap_id, current_user, db
    )

    query = (
        select(MindmapNodeChat)
        .where(
            MindmapNodeChat.mindmap_id == mindmap_id,
            MindmapNodeChat.user_id == current_user.id,
        )
        .order_by(MindmapNodeChat.id.asc())
        .limit(limit + 1)
    )
    if before_id is not None:
        query = query.where(MindmapNodeChat.id < before_id)

    result = await db.execute(query)
    rows = result.scalars().all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    return ChatHistoryResponse(
        messages=[ChatMessageOut.model_validate(r) for r in rows],
        has_more=has_more,
    )


@router.post("/{mindmap_id}/chat/ask", response_model=AskResponse)
async def ask_chat(
    mindmap_id: int,
    body: AskInThreadRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Ask a conversational question grounded in the file's knowledge base."""
    mindmap, file, classroom = await _get_mindmap_and_classroom(
        mindmap_id, current_user, db
    )

    if mindmap.status != MindmapStatus.READY:
        raise HTTPException(status_code=409, detail="Mindmap is not ready yet.")

    if not body.content.strip():
        raise HTTPException(status_code=422, detail="Question cannot be empty.")

    assistant_msg = await ask_in_thread(
        db=db,
        mindmap_id=mindmap_id,
        user_id=current_user.id,
        content=body.content.strip(),
        active_node_id=body.active_node_id,
        file_id=file.id,
        classroom_id=classroom.id,
    )

    return AskResponse(message=ChatMessageOut.model_validate(assistant_msg))


@router.delete("/{mindmap_id}/chat", status_code=status.HTTP_204_NO_CONTENT)
async def clear_chat(
    mindmap_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Clear all chat messages for this user in this mindmap."""
    mindmap, file, classroom = await _get_mindmap_and_classroom(
        mindmap_id, current_user, db
    )

    result = await db.execute(
        select(MindmapNodeChat).where(
            MindmapNodeChat.mindmap_id == mindmap_id,
            MindmapNodeChat.user_id == current_user.id,
        )
    )
    for msg in result.scalars().all():
        await db.delete(msg)

    await db.commit()
