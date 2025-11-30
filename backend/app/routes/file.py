from fastapi import APIRouter, UploadFile, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
import os

from app.lib.r2 import s3
from app.database.session import get_db
from app.models.file import File, ProcessingStatus
from app.models.folder import Folder
from app.models.classroom import Classroom
from app.schemas.file import FileOut, FileWithTopics
from app.schemas.topic import TopicOut
from app.dependencies.auth import get_current_user
from app.services.file_processor import file_processor
from app.services.langchain_vector_store import langchain_vector_store
from dotenv import load_dotenv

router = APIRouter(prefix="/files", tags=["Files"])
load_dotenv()


@router.post("/upload/{folder_id}", response_model=FileOut, status_code=status.HTTP_201_CREATED)
async def upload_file(
    folder_id: int,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Upload file and trigger background processing
    
    Process:
    1. Validate file type and user access
    2. Upload to R2 storage
    3. Create database record
    4. Trigger background processing (extract text → embeddings → topics)
    """
    # Verify folder exists and user has access
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
    if current_user not in classroom.members:
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")

    # Validate file type
    allowed_extensions = [".pdf", ".docx", ".pptx", ".txt"]
    file_extension = os.path.splitext(file.filename)[1].lower()
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Supported types: {', '.join(allowed_extensions)}"
        )

    # Read file content
    content = await file.read()
    file_size = len(content)
    
    # Generate S3 key
    file_key = f"folders/{folder_id}/{file.filename}"
    
    # Upload to R2
    try:
        s3.put_object(
            Bucket=os.getenv("R2_BUCKET_NAME"),
            Key=file_key,
            Body=content,
            ContentType=file.content_type
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

    # Generate file URL
    file_url = f"https://{os.getenv('R2_BUCKET_NAME')}.{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com/{file_key}"

    # Save to database with PENDING status
    new_file = File(
        filename=file.filename,
        file_url=file_url,
        file_key=file_key,
        file_type=file_extension.strip('.'),
        file_size=file_size,
        processing_status=ProcessingStatus.PENDING,
        folder_id=folder_id
    )
    db.add(new_file)
    db.commit()
    db.refresh(new_file)
    
    # Trigger background processing
    background_tasks.add_task(
        file_processor.process_file,
        file_id=new_file.id,
        file_content=content,
        filename=file.filename
    )

    return new_file


@router.get("/folder/{folder_id}", response_model=List[FileOut])
def get_files(
    folder_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get all files in a folder"""
    folder = db.query(Folder).filter_by(id=folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    # Check access
    classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
    if current_user not in classroom.members:
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")
        
    files = db.query(File).filter_by(folder_id=folder_id).all()
    return files


@router.get("/{file_id}", response_model=FileWithTopics)
def get_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get a specific file with its topics"""
    file = db.query(File).filter_by(id=file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Check access
    folder = db.query(Folder).filter(Folder.id == file.folder_id).first()
    classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
    if current_user not in classroom.members:
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")
    
    return file


@router.get("/{file_id}/status")
def get_file_status(
    file_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Check processing status of a file
    
    Returns:
        - status: pending, processing, completed, failed
        - processed_at: timestamp when completed
        - topics_count: number of topics extracted
    """
    file = db.query(File).filter_by(id=file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Check access
    folder = db.query(Folder).filter(Folder.id == file.folder_id).first()
    classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
    if current_user not in classroom.members:
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")
    
    return {
        "file_id": file.id,
        "filename": file.filename,
        "status": file.processing_status.value,
        "processed_at": file.processed_at,
        "topics_count": len(file.topics)
    }


@router.get("/{file_id}/topics", response_model=List[TopicOut])
def get_file_topics(
    file_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get all topics for a file"""
    file = db.query(File).filter_by(id=file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Check access
    folder = db.query(Folder).filter(Folder.id == file.folder_id).first()
    classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
    if current_user not in classroom.members:
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")
    
    # Return topics ordered by their order field
    from app.models.topic import Topic
    topics = db.query(Topic).filter(
        Topic.file_id == file_id
    ).order_by(Topic.order).all()
    
    return topics


@router.get("/{file_id}/download")
async def download_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get a pre-signed download URL for a specific file"""
    file = db.query(File).filter_by(id=file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Check access
    folder = db.query(Folder).filter(Folder.id == file.folder_id).first()
    classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
    if current_user not in classroom.members:
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")
    
    # Generate presigned URL that expires in 1 hour
    url = s3.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': os.getenv("R2_BUCKET_NAME"),
            'Key': file.file_key
        },
        ExpiresIn=3600
    )
    
    return {"download_url": url}


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Delete a file (removes from database, R2, and LangChain vector store)
    """
    file = db.query(File).filter_by(id=file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Check access (must be classroom owner)
    folder = db.query(Folder).filter(Folder.id == file.folder_id).first()
    classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
    
    if classroom.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only classroom owner can delete files")
    
    try:
        # Delete from R2
        s3.delete_object(
            Bucket=os.getenv("R2_BUCKET_NAME"),
            Key=file.file_key
        )
        
        # Delete from LangChain vector store
        langchain_vector_store.delete_file_chunks(classroom.id, file_id)
        
        # Delete from database (cascade will delete topics and chat messages)
        db.delete(file)
        db.commit()
        
        return None
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")









#OLD CODE



# from fastapi import APIRouter, UploadFile, Depends, HTTPException, status, BackgroundTasks
# from sqlalchemy.orm import Session
# from typing import List
# import os

# from app.lib.r2 import s3
# from app.database.session import get_db
# from app.models.file import File, ProcessingStatus
# from app.models.folder import Folder
# from app.models.classroom import Classroom
# from app.schemas.file import FileOut, FileWithTopics
# from app.schemas.topic import TopicOut
# from app.dependencies.auth import get_current_user
# from app.services.file_processor import file_processor
# from dotenv import load_dotenv

# router = APIRouter(prefix="/files", tags=["Files"])
# load_dotenv()


# @router.post("/upload/{folder_id}", response_model=FileOut, status_code=status.HTTP_201_CREATED)
# async def upload_file(
#     folder_id: int,
#     file: UploadFile,
#     background_tasks: BackgroundTasks,
#     db: Session = Depends(get_db),
#     current_user=Depends(get_current_user)
# ):
#     """
#     Upload file and trigger background processing
    
#     Process:
#     1. Validate file type and user access
#     2. Upload to R2 storage
#     3. Create database record
#     4. Trigger background processing (extract text → embeddings → topics)
#     """
#     # Verify folder exists and user has access
#     folder = db.query(Folder).filter(Folder.id == folder_id).first()
#     if not folder:
#         raise HTTPException(status_code=404, detail="Folder not found")
    
#     classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
#     if current_user not in classroom.members:
#         raise HTTPException(status_code=403, detail="You are not a member of this classroom")

#     # Validate file type
#     allowed_extensions = [".pdf", ".docx", ".pptx", ".txt"]
#     file_extension = os.path.splitext(file.filename)[1].lower()
#     if file_extension not in allowed_extensions:
#         raise HTTPException(
#             status_code=400,
#             detail=f"File type not allowed. Supported types: {', '.join(allowed_extensions)}"
#         )

#     # Read file content
#     content = await file.read()
#     file_size = len(content)
    
#     # Generate S3 key
#     file_key = f"folders/{folder_id}/{file.filename}"
    
#     # Upload to R2
#     try:
#         s3.put_object(
#             Bucket=os.getenv("R2_BUCKET_NAME"),
#             Key=file_key,
#             Body=content,
#             ContentType=file.content_type
#         )
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

#     # Generate file URL
#     file_url = f"https://{os.getenv('R2_BUCKET_NAME')}.{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com/{file_key}"

#     # Save to database with PENDING status
#     new_file = File(
#         filename=file.filename,
#         file_url=file_url,
#         file_key=file_key,
#         file_type=file_extension.strip('.'),
#         file_size=file_size,
#         processing_status=ProcessingStatus.PENDING,
#         folder_id=folder_id
#     )
#     db.add(new_file)
#     db.commit()
#     db.refresh(new_file)
    
#     # Trigger background processing
#     background_tasks.add_task(
#         file_processor.process_file,
#         file_id=new_file.id,
#         file_content=content,
#         filename=file.filename
#     )

#     return new_file


# @router.get("/folder/{folder_id}", response_model=List[FileOut])
# def get_files(
#     folder_id: int,
#     db: Session = Depends(get_db),
#     current_user=Depends(get_current_user)
# ):
#     """Get all files in a folder"""
#     folder = db.query(Folder).filter_by(id=folder_id).first()
#     if not folder:
#         raise HTTPException(status_code=404, detail="Folder not found")
    
#     # Check access
#     classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
#     if current_user not in classroom.members:
#         raise HTTPException(status_code=403, detail="You are not a member of this classroom")
        
#     files = db.query(File).filter_by(folder_id=folder_id).all()
#     return files


# @router.get("/{file_id}", response_model=FileWithTopics)
# def get_file(
#     file_id: int,
#     db: Session = Depends(get_db),
#     current_user=Depends(get_current_user)
# ):
#     """Get a specific file with its topics"""
#     file = db.query(File).filter_by(id=file_id).first()
#     if not file:
#         raise HTTPException(status_code=404, detail="File not found")
    
#     # Check access
#     folder = db.query(Folder).filter(Folder.id == file.folder_id).first()
#     classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
#     if current_user not in classroom.members:
#         raise HTTPException(status_code=403, detail="You are not a member of this classroom")
    
#     return file


# @router.get("/{file_id}/status")
# def get_file_status(
#     file_id: int,
#     db: Session = Depends(get_db),
#     current_user=Depends(get_current_user)
# ):
#     """
#     Check processing status of a file
    
#     Returns:
#         - status: pending, processing, completed, failed
#         - processed_at: timestamp when completed
#         - topics_count: number of topics extracted
#     """
#     file = db.query(File).filter_by(id=file_id).first()
#     if not file:
#         raise HTTPException(status_code=404, detail="File not found")
    
#     # Check access
#     folder = db.query(Folder).filter(Folder.id == file.folder_id).first()
#     classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
#     if current_user not in classroom.members:
#         raise HTTPException(status_code=403, detail="You are not a member of this classroom")
    
#     return {
#         "file_id": file.id,
#         "filename": file.filename,
#         "status": file.processing_status.value,
#         "processed_at": file.processed_at,
#         "topics_count": len(file.topics)
#     }


# @router.get("/{file_id}/topics", response_model=List[TopicOut])
# def get_file_topics(
#     file_id: int,
#     db: Session = Depends(get_db),
#     current_user=Depends(get_current_user)
# ):
#     """Get all topics for a file"""
#     file = db.query(File).filter_by(id=file_id).first()
#     if not file:
#         raise HTTPException(status_code=404, detail="File not found")
    
#     # Check access
#     folder = db.query(Folder).filter(Folder.id == file.folder_id).first()
#     classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
#     if current_user not in classroom.members:
#         raise HTTPException(status_code=403, detail="You are not a member of this classroom")
    
#     # Return topics ordered by their order field
#     from app.models.topic import Topic
#     topics = db.query(Topic).filter(
#         Topic.file_id == file_id
#     ).order_by(Topic.order).all()
    
#     return topics


# @router.get("/{file_id}/download")
# async def download_file(
#     file_id: int,
#     db: Session = Depends(get_db),
#     current_user=Depends(get_current_user)
# ):
#     """Get a pre-signed download URL for a specific file"""
#     file = db.query(File).filter_by(id=file_id).first()
#     if not file:
#         raise HTTPException(status_code=404, detail="File not found")
    
#     # Check access
#     folder = db.query(Folder).filter(Folder.id == file.folder_id).first()
#     classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
#     if current_user not in classroom.members:
#         raise HTTPException(status_code=403, detail="You are not a member of this classroom")
    
#     # Generate presigned URL that expires in 1 hour
#     url = s3.generate_presigned_url(
#         'get_object',
#         Params={
#             'Bucket': os.getenv("R2_BUCKET_NAME"),
#             'Key': file.file_key
#         },
#         ExpiresIn=3600
#     )
    
#     return {"download_url": url}


# @router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
# def delete_file(
#     file_id: int,
#     db: Session = Depends(get_db),
#     current_user=Depends(get_current_user)
# ):
#     """
#     Delete a file (removes from database, R2, and vector store)
#     """
#     file = db.query(File).filter_by(id=file_id).first()
#     if not file:
#         raise HTTPException(status_code=404, detail="File not found")
    
#     # Check access (must be classroom owner)
#     folder = db.query(Folder).filter(Folder.id == file.folder_id).first()
#     classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
    
#     if classroom.owner_id != current_user.id:
#         raise HTTPException(status_code=403, detail="Only classroom owner can delete files")
    
#     try:
#         # Delete from R2
#         s3.delete_object(
#             Bucket=os.getenv("R2_BUCKET_NAME"),
#             Key=file.file_key
#         )
        
#         # Delete from vector store
#         from app.services.vector_store import vector_store
#         vector_store.delete_file_chunks(classroom.id, file_id)
        
#         # Delete from database (cascade will delete topics and chat messages)
#         db.delete(file)
#         db.commit()
        
#         return None
        
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")