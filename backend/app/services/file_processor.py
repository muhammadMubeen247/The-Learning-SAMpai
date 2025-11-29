"""
File Processing Service
Orchestrates background processing pipeline for uploaded files
NOW USING: LangChain document processor AND LangChain vector store
"""

import logging
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from app.models.file import File, ProcessingStatus
from app.models.folder import Folder

# LangChain document processor
from app.services.langchain_document_processor import langchain_document_processor

# OLD: from app.services.vector_store import vector_store
# NEW: LangChain vector store
from app.services.langchain_vector_store import langchain_vector_store

from app.services.topic_extractor import topic_extractor
from app.services.topic_service import save_topics_to_db
from app.database.session import SessionLocal

logger = logging.getLogger(__name__)


class FileProcessor:
    """
    Handles the complete file processing pipeline
    NOW USING: Full LangChain integration (Phase 2 complete)
    """
    
    def __init__(self):
        # LangChain document processor (Phase 1)
        self.document_processor = langchain_document_processor
        
        # LangChain vector store (Phase 2)
        self.vector_store = langchain_vector_store
        
        # Topic extractor (unchanged)
        self.topic_extractor = topic_extractor
    
    async def process_file(
        self,
        file_id: int,
        file_content: bytes,
        filename: str
    ) -> bool:
        """
        Complete processing pipeline for uploaded file
        FULLY USING: LangChain for all operations
        """
        db = SessionLocal()
        
        try:
            # Step 0: Get file and update status to PROCESSING
            file = db.query(File).filter(File.id == file_id).first()
            if not file:
                logger.error(f"File {file_id} not found")
                return False
            
            file.processing_status = ProcessingStatus.PROCESSING
            db.commit()
            
            logger.info(f"[LANGCHAIN] Starting processing for file {file_id}: {filename}")
            
            # Get classroom_id for vector store
            folder = db.query(Folder).filter(Folder.id == file.folder_id).first()
            if not folder:
                raise ValueError(f"Folder {file.folder_id} not found")
            
            classroom_id = folder.classroom_id
            
            # Step 1: Extract text and create chunks (LANGCHAIN)
            logger.info(f"[{file_id}] Step 1: LangChain document processing...")
            chunks = self.document_processor.process_document(file_content, filename)
            
            if not chunks:
                raise ValueError("No chunks created from document")
            
            logger.info(f"[{file_id}] ✓ Created {len(chunks)} chunks with LangChain")
            
            # Step 2: Generate embeddings and store (LANGCHAIN CHROMA)
            logger.info(f"[{file_id}] Step 2: LangChain Chroma vector store...")
            vector_result = self.vector_store.add_document_chunks(
                classroom_id=classroom_id,
                file_id=file_id,
                chunks=chunks
            )
            
            logger.info(f"[{file_id}] ✓ Stored {vector_result['chunks_added']} chunks in LangChain Chroma")
            
            # Step 3: Extract topics using GPT
            logger.info(f"[{file_id}] Step 3: Extracting topics...")
            topics_data = self.topic_extractor.extract_topics_with_fallback(
                chunks=chunks,
                filename=filename
            )
            
            logger.info(f"[{file_id}] ✓ Extracted {len(topics_data)} topics")
            
            # Step 4: Save topics to database
            logger.info(f"[{file_id}] Step 4: Saving topics to database...")
            saved_topics = save_topics_to_db(
                db=db,
                file_id=file_id,
                topics_data=topics_data
            )
            
            logger.info(f"[{file_id}] ✓ Saved {len(saved_topics)} topics")
            
            # Step 5: Update file status to COMPLETED
            file.processing_status = ProcessingStatus.COMPLETED
            file.processed_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"[{file_id}] ✅ Processing completed successfully [FULL LANGCHAIN PIPELINE]")
            
            return True
            
        except Exception as e:
            logger.error(f"[{file_id}] ❌ Processing failed: {str(e)}", exc_info=True)
            
            # Update status to FAILED
            try:
                file = db.query(File).filter(File.id == file_id).first()
                if file:
                    file.processing_status = ProcessingStatus.FAILED
                    db.commit()
            except Exception as update_error:
                logger.error(f"Failed to update file status: {update_error}")
            
            return False
            
        finally:
            db.close()


# Singleton instance
file_processor = FileProcessor()














#OLD CODE

# """
# File Processing Service
# Orchestrates background processing pipeline for uploaded files
# NOW USING: LangChain document processor
# """

# import logging
# from sqlalchemy.orm import Session
# from datetime import datetime
# from typing import Optional

# from app.models.file import File, ProcessingStatus
# from app.models.folder import Folder

# # OLD: from app.services.document_processor import document_processor
# # NEW: Use LangChain processor
# from app.services.langchain_document_processor import langchain_document_processor

# from app.services.vector_store import vector_store
# from app.services.topic_extractor import topic_extractor
# from app.services.topic_service import save_topics_to_db
# from app.database.session import SessionLocal

# logger = logging.getLogger(__name__)


# class FileProcessor:
#     """
#     Handles the complete file processing pipeline
#     NOW USING: LangChain for document processing
#     """
    
#     def __init__(self):
#         # NEW: Use LangChain processor
#         self.document_processor = langchain_document_processor
#         self.vector_store = vector_store
#         self.topic_extractor = topic_extractor
    
#     async def process_file(
#         self,
#         file_id: int,
#         file_content: bytes,
#         filename: str
#     ) -> bool:
#         """
#         Complete processing pipeline for uploaded file
#         """
#         db = SessionLocal()
        
#         try:
#             # Step 0: Get file and update status to PROCESSING
#             file = db.query(File).filter(File.id == file_id).first()
#             if not file:
#                 logger.error(f"File {file_id} not found")
#                 return False
            
#             file.processing_status = ProcessingStatus.PROCESSING
#             db.commit()
            
#             logger.info(f"Starting processing for file {file_id}: {filename}")
            
#             # Get classroom_id for vector store
#             folder = db.query(Folder).filter(Folder.id == file.folder_id).first()
#             if not folder:
#                 raise ValueError(f"Folder {file.folder_id} not found")
            
#             classroom_id = folder.classroom_id
            
#             # Step 1: Extract text and create chunks (NOW WITH LANGCHAIN)
#             logger.info(f"[{file_id}] Step 1: Extracting text with LangChain...")
#             chunks = self.document_processor.process_document(file_content, filename)
            
#             if not chunks:
#                 raise ValueError("No chunks created from document")
            
#             logger.info(f"[{file_id}] Created {len(chunks)} chunks")
            
#             # Step 2: Generate embeddings and store in ChromaDB (LANGCHAIN EMBEDDINGS)
#             logger.info(f"[{file_id}] Step 2: Generating LangChain embeddings...")
#             vector_result = self.vector_store.add_document_chunks(
#                 classroom_id=classroom_id,
#                 file_id=file_id,
#                 chunks=chunks
#             )
            
#             logger.info(f"[{file_id}] Stored {vector_result['chunks_added']} chunks in vector DB")
            
#             # Step 3: Extract topics using GPT
#             logger.info(f"[{file_id}] Step 3: Extracting topics...")
#             topics_data = self.topic_extractor.extract_topics_with_fallback(
#                 chunks=chunks,
#                 filename=filename
#             )
            
#             logger.info(f"[{file_id}] Extracted {len(topics_data)} topics")
            
#             # Step 4: Save topics to database
#             logger.info(f"[{file_id}] Step 4: Saving topics to database...")
#             saved_topics = save_topics_to_db(
#                 db=db,
#                 file_id=file_id,
#                 topics_data=topics_data
#             )
            
#             logger.info(f"[{file_id}] Saved {len(saved_topics)} topics")
            
#             # Step 5: Update file status to COMPLETED
#             file.processing_status = ProcessingStatus.COMPLETED
#             file.processed_at = datetime.utcnow()
#             db.commit()
            
#             logger.info(f"[{file_id}] ✅ Processing completed successfully with LangChain")
            
#             return True
            
#         except Exception as e:
#             logger.error(f"[{file_id}] ❌ Processing failed: {str(e)}", exc_info=True)
            
#             # Update status to FAILED
#             try:
#                 file = db.query(File).filter(File.id == file_id).first()
#                 if file:
#                     file.processing_status = ProcessingStatus.FAILED
#                     db.commit()
#             except Exception as update_error:
#                 logger.error(f"Failed to update file status: {update_error}")
            
#             return False
            
#         finally:
#             db.close()


# # Singleton instance
# file_processor = FileProcessor()







# #OLD CODE


# # """
# # File Processing Service
# # Orchestrates background processing pipeline for uploaded files
# # """

# # import logging
# # from sqlalchemy.orm import Session
# # from datetime import datetime
# # from typing import Optional

# # from app.models.file import File, ProcessingStatus
# # from app.models.folder import Folder
# # from app.services.document_processor import document_processor
# # from app.services.vector_store import vector_store
# # from app.services.topic_extractor import topic_extractor
# # from app.services.topic_service import save_topics_to_db
# # from app.database.session import SessionLocal

# # logger = logging.getLogger(__name__)


# # class FileProcessor:
# #     """
# #     Handles the complete file processing pipeline
# #     """
    
# #     def __init__(self):
# #         self.document_processor = document_processor
# #         self.vector_store = vector_store
# #         self.topic_extractor = topic_extractor
    
# #     async def process_file(
# #         self,
# #         file_id: int,
# #         file_content: bytes,
# #         filename: str
# #     ) -> bool:
# #         """
# #         Complete processing pipeline for uploaded file
        
# #         Pipeline:
# #         1. Update status to PROCESSING
# #         2. Extract text and create chunks
# #         3. Generate embeddings and store in ChromaDB
# #         4. Extract topics using GPT
# #         5. Save topics to database
# #         6. Update status to COMPLETED
        
# #         Args:
# #             file_id: Database ID of file
# #             file_content: File bytes
# #             filename: Original filename
            
# #         Returns:
# #             True if successful, False otherwise
# #         """
# #         # Create a new database session for background task
# #         db = SessionLocal()
        
# #         try:
# #             # Step 0: Get file and update status to PROCESSING
# #             file = db.query(File).filter(File.id == file_id).first()
# #             if not file:
# #                 logger.error(f"File {file_id} not found")
# #                 return False
            
# #             file.processing_status = ProcessingStatus.PROCESSING
# #             db.commit()
            
# #             logger.info(f"Starting processing for file {file_id}: {filename}")
            
# #             # Get classroom_id for vector store
# #             folder = db.query(Folder).filter(Folder.id == file.folder_id).first()
# #             if not folder:
# #                 raise ValueError(f"Folder {file.folder_id} not found")
            
# #             classroom_id = folder.classroom_id
            
# #             # Step 1: Extract text and create chunks
# #             logger.info(f"[{file_id}] Step 1: Extracting text and chunking...")
# #             chunks = self.document_processor.process_document(file_content, filename)
            
# #             if not chunks:
# #                 raise ValueError("No chunks created from document")
            
# #             logger.info(f"[{file_id}] Created {len(chunks)} chunks")
            
# #             # Step 2: Generate embeddings and store in ChromaDB
# #             logger.info(f"[{file_id}] Step 2: Generating embeddings and storing in vector DB...")
# #             vector_result = self.vector_store.add_document_chunks(
# #                 classroom_id=classroom_id,
# #                 file_id=file_id,
# #                 chunks=chunks
# #             )
            
# #             logger.info(f"[{file_id}] Stored {vector_result['chunks_added']} chunks in vector DB")
            
# #             # Step 3: Extract topics using GPT
# #             logger.info(f"[{file_id}] Step 3: Extracting topics...")
# #             topics_data = self.topic_extractor.extract_topics_with_fallback(
# #                 chunks=chunks,
# #                 filename=filename
# #             )
            
# #             logger.info(f"[{file_id}] Extracted {len(topics_data)} topics")
            
# #             # Step 4: Save topics to database
# #             logger.info(f"[{file_id}] Step 4: Saving topics to database...")
# #             saved_topics = save_topics_to_db(
# #                 db=db,
# #                 file_id=file_id,
# #                 topics_data=topics_data
# #             )
            
# #             logger.info(f"[{file_id}] Saved {len(saved_topics)} topics")
            
# #             # Step 5: Update file status to COMPLETED
# #             file.processing_status = ProcessingStatus.COMPLETED
# #             file.processed_at = datetime.utcnow()
# #             db.commit()
            
# #             logger.info(f"[{file_id}] ✅ Processing completed successfully")
            
# #             return True
            
# #         except Exception as e:
# #             logger.error(f"[{file_id}] ❌ Processing failed: {str(e)}", exc_info=True)
            
# #             # Update status to FAILED
# #             try:
# #                 file = db.query(File).filter(File.id == file_id).first()
# #                 if file:
# #                     file.processing_status = ProcessingStatus.FAILED
# #                     db.commit()
# #             except Exception as update_error:
# #                 logger.error(f"Failed to update file status: {update_error}")
            
# #             return False
            
# #         finally:
# #             db.close()


# # # Singleton instance
# # file_processor = FileProcessor()