from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database.base import Base

class Folder(Base):
    __tablename__ = "folders"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

    classroom_id = Column(Integer, ForeignKey("classrooms.id"), nullable=False)
    classroom = relationship("Classroom", back_populates="folders")

    files = relationship("File", back_populates="folder", cascade="all, delete-orphan")
