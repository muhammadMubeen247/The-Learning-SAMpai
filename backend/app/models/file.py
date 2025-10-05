from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database.base import Base

class File(Base):
    __tablename__ = "files"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    file_url = Column(String, nullable=False)  # store path/URL of file
    description = Column(String, nullable=True)
    file_key = Column(String, nullable=False)  # store the R2 object key

    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=False)
    folder = relationship("Folder", back_populates="files")
