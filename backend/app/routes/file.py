import logging
import os

from fastapi import APIRouter, UploadFile, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, exists
from typing import List

from app.lib.r2 import s3
from app.database.session import get_db
from app.models.file import File, ProcessingStatus
from app.models.folder import Folder
from app.models.classroom import Classroom, classroom_members
from app.schemas.file import FileOut
from app.dependencies.auth import get_current_user
from app.services.file_processor import file_processor
from app.services.classroom_rag import classroom_rag_service
from dotenv import load_dotenv

router = APIRouter(prefix="/files", tags=["Files"])
logger = logging.getLogger(__name__)
load_dotenv()


async def _check_member(db: AsyncSession, classroom_id: int, user_id: int) -> bool:
    return await db.scalar(
        select(exists().where(
            (classroom_members.c.classroom_id == classroom_id) &
            (classroom_members.c.user_id == user_id)
        ))
    )


@router.post("/upload/{folder_id}", response_model=FileOut, status_code=status.HTTP_201_CREATED)
async def upload_file(
    folder_id: int,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Folder).where(Folder.id == folder_id))
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    if not await _check_member(db, folder.classroom_id, current_user.id):
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")

    allowed_extensions = [".pdf", ".docx", ".pptx", ".txt"]
    file_extension = os.path.splitext(file.filename)[1].lower()
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Supported types: {', '.join(allowed_extensions)}",
        )

    content = await file.read()
    file_size = len(content)
    file_key = f"folders/{folder_id}/{file.filename}"

    try:
        s3.put_object(
            Bucket=os.getenv("R2_BUCKET_NAME"),
            Key=file_key,
            Body=content,
            ContentType=file.content_type,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {e}")

    r2_endpoint = os.getenv("R2_ENDPOINT", "").rstrip("/")
    file_url = f"{r2_endpoint}/{os.getenv('R2_BUCKET_NAME')}/{file_key}"

    new_file = File(
        filename=file.filename,
        file_url=file_url,
        file_key=file_key,
        file_type=file_extension.strip("."),
        file_size=file_size,
        processing_status=ProcessingStatus.PENDING,
        folder_id=folder_id,
    )
    db.add(new_file)
    await db.commit()
    await db.refresh(new_file)

    logger.info(
        f"[file] UPLOAD file_id={new_file.id} filename='{file.filename}' "
        f"folder_id={folder_id} size={file_size}B user_id={current_user.id}"
    )

    background_tasks.add_task(
        file_processor.process_file,
        file_id=new_file.id,
        file_content=content,
        filename=file.filename,
    )

    return new_file


@router.get("/folder/{folder_id}", response_model=List[FileOut])
async def get_files(
    folder_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Folder).where(Folder.id == folder_id))
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    if not await _check_member(db, folder.classroom_id, current_user.id):
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")

    result = await db.execute(select(File).where(File.folder_id == folder_id))
    return result.scalars().all()


@router.get("/{file_id}", response_model=FileOut)
async def get_file(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(File).where(File.id == file_id))
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    result = await db.execute(select(Folder).where(Folder.id == file.folder_id))
    folder = result.scalar_one_or_none()

    if not await _check_member(db, folder.classroom_id, current_user.id):
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")

    return file


@router.get("/{file_id}/status")
async def get_file_status(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(File).where(File.id == file_id))
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    result = await db.execute(select(Folder).where(Folder.id == file.folder_id))
    folder = result.scalar_one_or_none()

    if not await _check_member(db, folder.classroom_id, current_user.id):
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")

    logger.debug(f"[file] STATUS_CHECK file_id={file_id} status={file.processing_status.value}")
    return {
        "file_id": file.id,
        "filename": file.filename,
        "status": file.processing_status.value,
        "processed_at": file.processed_at,
    }


@router.post("/{file_id}/reprocess", status_code=202)
async def reprocess_file(
    file_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(File).where(File.id == file_id))
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    result = await db.execute(select(Folder).where(Folder.id == file.folder_id))
    folder = result.scalar_one_or_none()

    if not await _check_member(db, folder.classroom_id, current_user.id):
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")

    try:
        response = s3.get_object(Bucket=os.getenv("R2_BUCKET_NAME"), Key=file.file_key)
        file_content = response["Body"].read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not fetch file from storage: {e}")

    file.processing_status = ProcessingStatus.PENDING
    await db.commit()

    logger.info(f"[file] REPROCESS file_id={file_id} filename='{file.filename}' user_id={current_user.id}")

    background_tasks.add_task(
        file_processor.process_file,
        file_id=file.id,
        file_content=file_content,
        filename=file.filename,
    )

    return {"detail": "Reprocessing started", "file_id": file_id}


@router.get("/{file_id}/download")
async def download_file(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(File).where(File.id == file_id))
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    result = await db.execute(select(Folder).where(Folder.id == file.folder_id))
    folder = result.scalar_one_or_none()

    if not await _check_member(db, folder.classroom_id, current_user.id):
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")

    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": os.getenv("R2_BUCKET_NAME"), "Key": file.file_key},
        ExpiresIn=3600,
    )

    logger.info(f"[file] DOWNLOAD file_id={file_id} user_id={current_user.id}")
    return {"download_url": url}


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(File).where(File.id == file_id))
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    result = await db.execute(select(Folder).where(Folder.id == file.folder_id))
    folder = result.scalar_one_or_none()

    result = await db.execute(select(Classroom).where(Classroom.id == folder.classroom_id))
    classroom = result.scalar_one_or_none()

    if classroom.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only classroom owner can delete files")

    logger.info(f"[file] DELETE file_id={file_id} user_id={current_user.id}")
    try:
        s3.delete_object(Bucket=os.getenv("R2_BUCKET_NAME"), Key=file.file_key)

        engine = await classroom_rag_service.get_engine(classroom.id)
        await engine.adelete_file(file.file_url)

        await db.delete(file)
        await db.commit()

        logger.info(f"[file] DELETE_OK file_id={file_id}")
        return None

    except Exception as e:
        await db.rollback()
        logger.error(f"[file] DELETE_FAIL file_id={file_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {e}")
