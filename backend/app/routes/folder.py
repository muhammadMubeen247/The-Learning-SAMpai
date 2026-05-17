import logging
import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.lib.r2 import s3
from app.database.session import get_db
from app.models.folder import Folder
from app.models.classroom import Classroom
from app.schemas.folder import FolderCreate, FolderOut
from app.dependencies.auth import get_current_user
from app.services.classroom_rag import classroom_rag_service

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


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Load folder with its files eagerly to avoid lazy-load errors
    result = await db.execute(
        select(Folder)
        .where(Folder.id == folder_id)
        .options(selectinload(Folder.files))
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    result = await db.execute(select(Classroom).where(Classroom.id == folder.classroom_id))
    classroom = result.scalar_one_or_none()
    if not classroom or classroom.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the classroom owner can delete folders")

    files = folder.files
    logger.info(
        f"[folder] DELETE folder_id={folder_id} name='{folder.name}' "
        f"file_count={len(files)} user_id={current_user.id}"
    )

    # Clean up external resources for each file.
    # Failures are logged as warnings — they do not abort the deletion.
    if files:
        engine = await classroom_rag_service.get_engine(classroom.id)
        for file in files:
            try:
                s3.delete_object(Bucket=os.getenv("R2_BUCKET_NAME"), Key=file.file_key)
            except Exception as exc:
                logger.warning(f"[folder] S3 delete failed file_id={file.id}: {exc}")
            try:
                await engine.adelete_file(file.file_url)
            except Exception as exc:
                logger.warning(f"[folder] RAG delete failed file_id={file.id}: {exc}")

    # Delete the folder — cascade removes contained files and all their related rows
    try:
        await db.delete(folder)
        await db.commit()
        logger.info(f"[folder] DELETE_OK folder_id={folder_id}")
        return None
    except Exception as exc:
        await db.rollback()
        logger.error(f"[folder] DELETE_FAIL folder_id={folder_id}: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to delete folder: {exc}")
