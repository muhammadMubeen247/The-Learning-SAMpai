from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.folder import Folder
from app.models.classroom import Classroom
from app.schemas.folder import FolderCreate, FolderOut
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/folders", tags=["folders"])

@router.post("/classroom/{classroom_id}", response_model=FolderOut)
def create_folder(classroom_id: int, folder: FolderCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    classroom = db.query(Classroom).filter(Classroom.id == classroom_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    if classroom.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owner can create folders")

    new_folder = Folder(name=folder.name, classroom_id=classroom_id)
    db.add(new_folder)
    db.commit()
    db.refresh(new_folder)
    return new_folder

@router.get("/classroom/{classroom_id}", response_model=list[FolderOut])
def get_folders(classroom_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    classroom = db.query(Classroom).filter(Classroom.id == classroom_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    return classroom.folders
