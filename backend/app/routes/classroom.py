import random, string
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.classroom import Classroom
from app.schemas.classroom import ClassroomCreate, ClassroomOut
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/classrooms", tags=["classrooms"])

def generate_class_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

@router.post("/create", response_model=ClassroomOut)
def create_classroom(
    classroom: ClassroomCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    # Generate a unique classroom code
    code = generate_class_code()
    while db.query(Classroom).filter(Classroom.code == code).first():
        code = generate_class_code()

    new_classroom = Classroom(
        name=classroom.name,
        description=classroom.description,
        code=code,
        owner_id=current_user.id
    )
    db.add(new_classroom)
    db.commit()
    db.refresh(new_classroom)

    # Also add creator as member
    new_classroom.members.append(current_user)
    db.commit()

    return new_classroom

@router.post("/join/{code}", response_model=ClassroomOut)
def join_classroom(
    code: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    classroom = db.query(Classroom).filter(Classroom.code == code).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    if current_user in classroom.members:
        raise HTTPException(status_code=400, detail="Already a member of this classroom")

    classroom.members.append(current_user)
    db.commit()
    db.refresh(classroom)
    return classroom

@router.get("/", response_model=list[ClassroomOut])
def get_my_classrooms(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return current_user.classrooms

@router.get("/{id}", response_model=ClassroomOut)
def get_classroom(
    id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    classroom = db.query(Classroom).filter(Classroom.id == id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    if current_user not in classroom.members:
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")

    return classroom
