from sqlalchemy import Column, Integer, String, ForeignKey, Table, DateTime
from sqlalchemy.orm import relationship
from app.database.base import Base
from datetime import datetime

# Association table for many-to-many relation
classroom_members = Table(
    "classroom_members",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("classroom_id", Integer, ForeignKey("classrooms.id"), primary_key=True),
)

class Classroom(Base):
    __tablename__ = "classrooms"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)
    code = Column(String, unique=True, index=True, nullable=False)  # 👈 join code
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


    folders = relationship("Folder", back_populates="classroom", cascade="all, delete-orphan")
    owner = relationship("User", back_populates="owned_classrooms")
    members = relationship("User", secondary=classroom_members, back_populates="classrooms")
