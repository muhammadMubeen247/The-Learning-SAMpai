import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.session import get_db
from app.models.folder import Folder
from app.models.classroom import Classroom
from app.schemas.folder import FolderCreate, FolderOut
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/folders", tags=["folders"])
logger = logging.getLogger(__name__)


@router.post("/classroom/{classroom_id}", response_model=FolderOut)
async def create_folder(
    classroom_id: int,
    folder: FolderCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Classroom).where(Classroom.id == classroom_id))
    classroom = result.scalar_one_or_none()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    if classroom.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owner can create folders")

    new_folder = Folder(name=folder.name, classroom_id=classroom_id)
    db.add(new_folder)
    await db.commit()
    await db.refresh(new_folder)
    # Re-fetch with files eagerly loaded to avoid lazy-load greenlet error
    result = await db.execute(
        select(Folder).where(Folder.id == new_folder.id).options(selectinload(Folder.files))
    )
    new_folder = result.scalar_one()
    logger.info(
        f"[folder] CREATE folder_id={new_folder.id} name='{new_folder.name}' "
        f"classroom_id={classroom_id} user_id={current_user.id}"
    )
    return new_folder


@router.get("/classroom/{classroom_id}", response_model=list[FolderOut])
async def get_folders(
    classroom_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Classroom).where(Classroom.id == classroom_id))
    classroom = result.scalar_one_or_none()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    result = await db.execute(
        select(Folder).where(Folder.classroom_id == classroom_id).options(selectinload(Folder.files))
    )
    folders = result.scalars().all()
    logger.info(f"[folder] LIST classroom_id={classroom_id} user_id={current_user.id} count={len(folders)}")
    return folders
