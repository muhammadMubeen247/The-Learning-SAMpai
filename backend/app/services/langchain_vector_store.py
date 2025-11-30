"""
LangChain Vector Store Service
Uses LangChain's Chroma wrapper for vector operations
Handles migration from old ChromaDB format
"""

import logging
from typing import List, Dict, Optional, Any
from pathlib import Path
import shutil

# LangChain imports
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain.schema import Document as LangChainDocument

from app.config.chroma_config import (
    CHROMA_DATA_DIR,
    OPENAI_API_KEY,
    EMBEDDING_MODEL,
    get_collection_name
)
from app.services.document_processor import DocumentChunk

logger = logging.getLogger(__name__)


class LangChainVectorStore:
    """
    Vector store using LangChain's Chroma wrapper
    Handles migration from old ChromaDB format
    """
    
    def __init__(self):
        """Initialize LangChain Chroma with OpenAI embeddings"""
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        # Initialize LangChain OpenAI Embeddings
        self.embeddings = OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            openai_api_key=OPENAI_API_KEY
        )
        
        self.embedding_model = EMBEDDING_MODEL
        self.persist_directory = CHROMA_DATA_DIR
        
        # Store active Chroma instances by classroom_id
        self._chroma_instances: Dict[int, Chroma] = {}
        
        logger.info(f"LangChain VectorStore initialized")
        logger.info(f"  Persist directory: {CHROMA_DATA_DIR}")
        logger.info(f"  Embedding model: {EMBEDDING_MODEL}")
    
    def _handle_incompatible_collection(self, classroom_id: int, collection_name: str) -> None:
        """
        Handle incompatible collection by deleting it
        
        This happens when migrating from old ChromaDB format to LangChain format
        
        Args:
            classroom_id: Classroom ID
            collection_name: Collection name to delete
        """
        logger.warning(f"Incompatible collection detected: {collection_name}")
        logger.warning(f"This collection was created with old ChromaDB format")
        logger.warning(f"Deleting and recreating with LangChain format...")
        
        try:
            # Delete the incompatible collection using direct ChromaDB client
            import chromadb
            from chromadb.config import Settings
            
            client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # Try to delete the collection
            try:
                client.delete_collection(name=collection_name)
                logger.info(f"Deleted incompatible collection: {collection_name}")
            except Exception as delete_error:
                logger.error(f"Failed to delete collection: {delete_error}")
                
                # Nuclear option: delete the collection directory
                collection_dir = Path(self.persist_directory)
                if collection_dir.exists():
                    logger.warning(f"Attempting to manually remove collection data...")
                    # Collection data is in subdirectories, but we can't safely identify which
                    # So we'll let the collection be recreated
            
            logger.info(f"Collection {collection_name} ready for recreation")
            
        except Exception as e:
            logger.error(f"Error handling incompatible collection: {e}")
    
    def get_chroma_collection(self, classroom_id: int) -> Chroma:
        """
        Get or create LangChain Chroma collection for a classroom
        
        Args:
            classroom_id: Classroom ID
            
        Returns:
            LangChain Chroma instance
        """
        # Return cached instance if exists
        if classroom_id in self._chroma_instances:
            return self._chroma_instances[classroom_id]
        
        collection_name = get_collection_name(classroom_id)
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                # Create LangChain Chroma instance
                chroma = Chroma(
                    collection_name=collection_name,
                    embedding_function=self.embeddings,
                    persist_directory=self.persist_directory,
                    collection_metadata={"classroom_id": classroom_id}
                )
                
                # Cache the instance
                self._chroma_instances[classroom_id] = chroma
                
                logger.info(f"[LangChain] Using Chroma collection: {collection_name}")
                
                return chroma
                
            except KeyError as e:
                if "'_type'" in str(e) and attempt == 0:
                    # Incompatible collection detected, handle it
                    logger.warning(f"Attempt {attempt + 1}: Incompatible collection format")
                    self._handle_incompatible_collection(classroom_id, collection_name)
                    # Retry on next iteration
                    continue
                else:
                    # Other KeyError or max retries reached
                    raise
                    
            except Exception as e:
                logger.error(f"Error accessing Chroma collection {collection_name}: {str(e)}")
                
                if "configuration" in str(e).lower() and attempt == 0:
                    # Might be compatibility issue
                    self._handle_incompatible_collection(classroom_id, collection_name)
                    continue
                
                raise
        
        # If we get here, all retries failed
        raise ValueError(f"Failed to create collection after {max_retries} attempts")
    
    def add_document_chunks(
        self,
        classroom_id: int,
        file_id: int,
        chunks: List[DocumentChunk]
    ) -> Dict[str, Any]:
        """
        Add document chunks to vector store using LangChain
        
        Args:
            classroom_id: Classroom the file belongs to
            file_id: Database ID of file
            chunks: List of DocumentChunk objects
            
        Returns:
            Dictionary with processing stats
        """
        try:
            chroma = self.get_chroma_collection(classroom_id)
            
            # Convert DocumentChunks to LangChain Documents
            documents = []
            ids = []
            
            for chunk in chunks:
                # Generate unique ID
                chunk_id = f"file_{file_id}_chunk_{chunk.chunk_index}"
                
                # Prepare metadata
                metadata = {
                    "file_id": file_id,
                    "chunk_index": chunk.chunk_index,
                    "page_number": chunk.page_number if chunk.page_number is not None else -1,
                    "slide_number": chunk.slide_number if chunk.slide_number is not None else -1,
                }
                
                # Add custom metadata
                if chunk.metadata:
                    metadata.update(chunk.metadata)
                
                # Create LangChain Document
                doc = LangChainDocument(
                    page_content=chunk.content,
                    metadata=metadata
                )
                
                documents.append(doc)
                ids.append(chunk_id)
            
            # Add to Chroma using LangChain
            logger.info(f"[LangChain] Adding {len(documents)} documents to Chroma...")
            chroma.add_documents(
                documents=documents,
                ids=ids
            )
            
            logger.info(f"[LangChain] Successfully added {len(chunks)} chunks to collection")
            
            return {
                "success": True,
                "chunks_added": len(chunks),
                "collection_name": get_collection_name(classroom_id),
                "file_id": file_id
            }
            
        except Exception as e:
            logger.error(f"Error adding chunks to LangChain Chroma: {str(e)}", exc_info=True)
            raise ValueError(f"Failed to add chunks: {str(e)}")
    
    def search_similar_chunks(
        self,
        classroom_id: int,
        query: str,
        file_id: Optional[int] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search for chunks similar to query using LangChain Chroma
        """
        try:
            chroma = self.get_chroma_collection(classroom_id)
            
            # Prepare filter for file_id if specified
            filter_dict = None
            if file_id is not None:
                filter_dict = {"file_id": file_id}
            
            # Search using LangChain
            logger.info(f"[LangChain] Searching for similar chunks (top_k={top_k})")
            
            if filter_dict:
                results = chroma.similarity_search_with_score(
                    query=query,
                    k=top_k,
                    filter=filter_dict
                )
            else:
                results = chroma.similarity_search_with_score(
                    query=query,
                    k=top_k
                )
            
            # Format results
            formatted_results = []
            for doc, score in results:
                formatted_results.append({
                    "id": f"file_{doc.metadata.get('file_id')}_chunk_{doc.metadata.get('chunk_index')}",
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "distance": score
                })
            
            logger.info(f"[LangChain] Found {len(formatted_results)} similar chunks")
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error searching LangChain Chroma: {str(e)}")
            raise ValueError(f"Failed to search: {str(e)}")
    
    def delete_file_chunks(self, classroom_id: int, file_id: int) -> bool:
        """Delete all chunks for a specific file"""
        try:
            chroma = self.get_chroma_collection(classroom_id)
            
            logger.info(f"[LangChain] Deleting chunks for file {file_id}")
            
            # Get all IDs matching the file_id filter
            all_docs = chroma.get(
                where={"file_id": file_id}
            )
            
            if all_docs and all_docs.get('ids'):
                chroma.delete(ids=all_docs['ids'])
                logger.info(f"[LangChain] Deleted {len(all_docs['ids'])} chunks for file {file_id}")
            else:
                logger.info(f"[LangChain] No chunks found for file {file_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting file chunks: {str(e)}")
            return False
    
    def delete_collection(self, classroom_id: int) -> bool:
        """Delete entire collection for a classroom"""
        try:
            collection_name = get_collection_name(classroom_id)
            
            # Remove from cache
            if classroom_id in self._chroma_instances:
                del self._chroma_instances[classroom_id]
            
            # Delete using direct client
            import chromadb
            from chromadb.config import Settings
            
            client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            client.delete_collection(name=collection_name)
            
            logger.info(f"[LangChain] Deleted collection: {collection_name}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting collection: {str(e)}")
            return False
    
    def get_collection_stats(self, classroom_id: int) -> Dict[str, Any]:
        """Get statistics about a classroom's collection"""
        try:
            chroma = self.get_chroma_collection(classroom_id)
            
            # Get count
            collection = chroma._collection
            count = collection.count()
            
            return {
                "collection_name": get_collection_name(classroom_id),
                "total_chunks": count,
                "classroom_id": classroom_id,
                "using_langchain": True
            }
            
        except Exception as e:
            logger.error(f"Error getting collection stats: {str(e)}")
            return {}
    
    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text"""
        return self.embeddings.embed_query(text)
    
    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts"""
        return self.embeddings.embed_documents(texts)


# Singleton instance
langchain_vector_store = LangChainVectorStore()