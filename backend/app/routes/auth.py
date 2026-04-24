import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from app.database.session import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserLogin
from app.utils.hashing import hash_password, verify_password
from app.utils.jwt_handler import create_access_token
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    logger.info(f"[auth] SIGNUP attempt username={payload.username} email={payload.email}")
    result = await db.execute(
        select(User).where(or_(User.email == payload.email, User.username == payload.username))
    )
    existing = result.scalar_one_or_none()
    if existing:
        logger.warning(f"[auth] SIGNUP_FAIL duplicate email={payload.email} or username={payload.username}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email or username already registered")

    new_user = User(
        email=payload.email,
        username=payload.username,
        hashed_password=hash_password(payload.password)
    )
    db.add(new_user)

    try:
        await db.commit()
        await db.refresh(new_user)
    except IntegrityError:
        await db.rollback()
        logger.warning(f"[auth] SIGNUP_FAIL integrity error email={payload.email}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to create user (duplicate?)")

    logger.info(f"[auth] SIGNUP_OK user_id={new_user.id} username={new_user.username}")
    return new_user


@router.post("/login", response_model=dict)
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    logger.info(f"[auth] LOGIN attempt email={payload.email}")
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        logger.warning(f"[auth] LOGIN_FAIL email={payload.email} reason=invalid_credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    access_token = create_access_token(data={"sub": str(user.id)})
    logger.info(f"[auth] LOGIN_OK user_id={user.id} email={user.email}")
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username
        }
    }


@router.post("/logout")
def logout():
    logger.info("[auth] LOGOUT")
    return {"message": "Logout successful"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    logger.info(f"[auth] ME user_id={current_user.id}")
    return current_user
