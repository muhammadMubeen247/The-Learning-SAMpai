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
        folder_id=folder_id
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    return db_file


@router.get("/folder/{folder_id}")
def get_files(folder_id: int, db: Session = Depends(get_db)):
    files = db.query(File).filter_by(folder_id=folder_id).all()
    return files
