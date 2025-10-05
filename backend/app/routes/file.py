from fastapi import APIRouter, UploadFile, Depends, HTTPException
from sqlalchemy.orm import Session
from app.lib.r2 import s3
from app.database.session import get_db
from app.models.file import File
from app.models.folder import Folder
from app.models.classroom import Classroom
from app.schemas.file import FileOut
from app.dependencies.auth import get_current_user
from dotenv import load_dotenv
import os

router = APIRouter(prefix="/files", tags=["Files"])

load_dotenv()

@router.post("/upload/{folder_id}", response_model=FileOut)
def upload_file(
    folder_id: int, 
    file: UploadFile, 
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # Get the folder
    folder = db.query(Folder).filter_by(id=folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    # Get the classroom associated with this folder
    classroom = db.query(Classroom).filter_by(id=folder.classroom_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    # Check if current user is the classroom owner
    if classroom.owner_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only classroom owner can upload files"
        )

    # Continue with file upload if user is authorized
    bucket = os.getenv("R2_BUCKET_NAME")
    if not bucket:
        raise HTTPException(status_code=500, detail="R2_BUCKET_NAME not configured")

    key = f"folders/{folder_id}/{file.filename}"

    # Upload to R2
    s3.upload_fileobj(file.file, bucket, key)

    # Generate file URL using the correct endpoint
    file_url = f"{os.getenv('R2_ENDPOINT')}/{bucket}/{key}"

    # Create file record
    db_file = File(
        filename=file.filename,
        file_url=file_url,
        folder_id=folder_id
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    return db_file


@router.get("/folder/{folder_id}", response_model=list[FileOut])
def get_files(folder_id: int, db: Session = Depends(get_db)):
    """Get all files in a folder"""
    folder = db.query(Folder).filter_by(id=folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
        
    files = db.query(File).filter_by(folder_id=folder_id).all()
    return files


@router.get("/{file_id}", response_model=FileOut)
def get_file(file_id: int, db: Session = Depends(get_db)):
    """Get a specific file by ID"""
    file = db.query(File).filter_by(id=file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    return file


@router.get("/{file_id}/download")
async def download_file(file_id: int, db: Session = Depends(get_db)):
    """Get a pre-signed download URL for a specific file"""
    file = db.query(File).filter_by(id=file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Generate presigned URL that expires in 1 hour
    url = s3.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': os.getenv("R2_BUCKET_NAME"),
            'Key': file.file_key  # using stored key
        },
        ExpiresIn=3600
    )
    
    return {"download_url": url}
