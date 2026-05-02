from sqlalchemy import Boolean, Column, Integer, String
from sqlalchemy.orm import relationship
from app.database.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_system = Column(Boolean, nullable=False, default=False)

    # Relationships
    owned_classrooms = relationship("Classroom", foreign_keys="Classroom.owner_id", back_populates="owner")
    classrooms = relationship("Classroom", secondary="classroom_members", back_populates="members")