from fastapi import APIRouter, UploadFile, Depends, HTTPException
from sqlalchemy.orm import Session
from app.lib.r2 import s3
from app.database.session import get_db
from app.models.file import File
from app.models.folder import Folder
from app.schemas.file import FileOut
from dotenv import load_dotenv
import os

router = APIRouter(prefix="/files", tags=["Files"])

load_dotenv()

@router.post("/upload/{folder_id}", response_model=FileOut)
def upload_file(folder_id: int, file: UploadFile, db: Session = Depends(get_db)):
    folder = db.query(Folder).filter_by(id=folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    bucket = os.getenv("R2_BUCKET_NAME")
    if not bucket:
        raise HTTPException(status_code=500, detail="R2_BUCKET_NAME not configured")

    key = f"folders/{folder_id}/{file.filename}"

    # Upload to R2
    s3.upload_fileobj(file.file, bucket, key)

    # Generate file URL using the correct endpoint
    file_url = f"{os.getenv('R2_ENDPOINT')}/{bucket}/{key}"

    # Create file record using correct field name (file_url instead of url)
    db_file = File(
        filename=file.filename,
        file_url=file_url,  # Changed from url to file_url to match model
        folder_id=folder_id,
        file_key=key  # Store the R2 object key
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
