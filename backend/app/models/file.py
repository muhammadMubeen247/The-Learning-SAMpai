from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.database.base import Base
from datetime import datetime
import enum

class ProcessingStatus(str, enum.Enum):
    """Enum for file processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class File(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_url = Column(Text, nullable=False)
    file_key = Column(String(500), nullable=False)  # S3/R2 key
    file_type = Column(String(50), nullable=True)   # e.g., "pdf", "docx", "pptx"
    file_size = Column(Integer, nullable=True)      # Size in bytes
    processing_status = Column(
        SQLEnum(ProcessingStatus),
        default=ProcessingStatus.PENDING,
        nullable=False
    )
    description = Column(Text, nullable=True)
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)  # When processing completed
    rag_doc_id = Column(String(512), nullable=True)  # LightRAG document hash ID

    # Relationships
    folder = relationship("Folder", back_populates="files")
    chat_messages = relationship("ChatMessage", back_populates="file", cascade="all, delete-orphan")
