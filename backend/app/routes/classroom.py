import logging
import random
import string

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, exists
from sqlalchemy.orm import selectinload

from app.database.session import get_db
from app.models.classroom import Classroom, classroom_members
from app.models.user import User
from app.schemas.classroom import ClassroomCreate, ClassroomOut
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/classrooms", tags=["classrooms"])
logger = logging.getLogger(__name__)


def _generate_code(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


async def _is_member(db: AsyncSession, classroom_id: int, user_id: int) -> bool:
    return await db.scalar(
        select(exists().where(
            (classroom_members.c.classroom_id == classroom_id) &
            (classroom_members.c.user_id == user_id)
        ))
    )


async def _load_classroom(db: AsyncSession, classroom_id: int) -> Classroom:
    result = await db.execute(
        select(Classroom)
        .options(selectinload(Classroom.members))
        .where(Classroom.id == classroom_id)
    )
    return result.scalar_one()


@router.post("/create", response_model=ClassroomOut)
async def create_classroom(
    classroom: ClassroomCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    code = _generate_code()
    while await db.scalar(select(exists().where(Classroom.code == code))):
        code = _generate_code()

    new_classroom = Classroom(
        name=classroom.name,
        description=classroom.description,
        code=code,
        owner_id=current_user.id,
    )
    db.add(new_classroom)
    await db.commit()
    await db.refresh(new_classroom)

    await db.execute(
        classroom_members.insert().values(
            classroom_id=new_classroom.id, user_id=current_user.id
        )
    )
    await db.commit()

    result = await _load_classroom(db, new_classroom.id)
    logger.info(
        f"[classroom] CREATE classroom_id={result.id} name='{result.name}' "
        f"code={result.code} owner_id={current_user.id}"
    )
    return result


@router.post("/join/{code}", response_model=ClassroomOut)
async def join_classroom(
    code: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Classroom).where(Classroom.code == code))
    classroom = result.scalar_one_or_none()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    if await _is_member(db, classroom.id, current_user.id):
        raise HTTPException(status_code=400, detail="Already a member of this classroom")

    await db.execute(
        classroom_members.insert().values(
            classroom_id=classroom.id, user_id=current_user.id
        )
    )
    await db.commit()

    loaded = await _load_classroom(db, classroom.id)
    logger.info(f"[classroom] JOIN classroom_id={loaded.id} user_id={current_user.id} code={code}")
    return loaded


@router.get("/", response_model=list[ClassroomOut])
async def get_my_classrooms(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.classrooms).selectinload(Classroom.members)
        )
        .where(User.id == current_user.id)
    )
    user = result.scalar_one()
    logger.info(f"[classroom] LIST user_id={current_user.id} count={len(user.classrooms)}")
    return user.classrooms


@router.get("/{id}", response_model=ClassroomOut)
async def get_classroom(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    exists_row = await db.scalar(select(exists().where(Classroom.id == id)))
    if not exists_row:
        raise HTTPException(status_code=404, detail="Classroom not found")

    if not await _is_member(db, id, current_user.id):
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")

    classroom = await _load_classroom(db, id)
    logger.info(f"[classroom] GET classroom_id={id} user_id={current_user.id}")
    return classroom
