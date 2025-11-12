from fastapi import APIRouter, UploadFile, Depends, HTTPException, status
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

@router.post("/upload/{folder_id}", response_model=FileOut, status_code=status.HTTP_201_CREATED)
async def upload_file(
    folder_id: int,
    file: UploadFile,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    # Verify folder exists and user has access
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
    if current_user not in classroom.members:
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")

    # Validate file type
    allowed_extensions = [".pdf", ".docx", ".pptx"]
    file_extension = os.path.splitext(file.filename)[1].lower()
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Supported types: {', '.join(allowed_extensions)}"
        )

    # Read file content
    content = await file.read()
    
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

    # Save to database
    new_file = File(
        filename=file.filename,
        file_url=file_url,
        file_key=file_key, 
        folder_id=folder_id
    )
    db.add(new_file)
    db.commit()
    db.refresh(new_file)

    return new_file


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
