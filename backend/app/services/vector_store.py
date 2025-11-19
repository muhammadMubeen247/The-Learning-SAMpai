"""
Vector Store Service
Manages ChromaDB collections for document embeddings and similarity search
"""

import logging
from typing import List, Dict, Optional, Any
import chromadb
from chromadb.config import Settings
from openai import OpenAI
import json

from app.config.chroma_config import (
    CHROMA_DATA_DIR,
    OPENAI_API_KEY,
    EMBEDDING_MODEL,
    get_collection_name
)
from app.services.document_processor import DocumentChunk

logger = logging.getLogger(__name__)


class VectorStore:
    """
    Manages document embeddings in ChromaDB
    Organizes collections by classroom_id
    """
    
    def __init__(self):
        """Initialize ChromaDB client and OpenAI client"""
        # Initialize ChromaDB with persistent storage
        self.chroma_client = chromadb.PersistentClient(
            path=CHROMA_DATA_DIR,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Initialize OpenAI client
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        self.openai_client = OpenAI(api_key=OPENAI_API_KEY)
        self.embedding_model = EMBEDDING_MODEL
        
        logger.info(f"VectorStore initialized with ChromaDB at {CHROMA_DATA_DIR}")
        logger.info(f"Using embedding model: {EMBEDDING_MODEL}")
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for text using OpenAI
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector (list of floats)
        """
        try:
            response = self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            
            embedding = response.data[0].embedding
            logger.debug(f"Generated embedding with {len(embedding)} dimensions")
            
            return embedding
            
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            raise ValueError(f"Failed to generate embedding: {str(e)}")
    
    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts (batch processing)
        More efficient than calling generate_embedding() multiple times
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        try:
            # OpenAI allows up to 2048 texts per batch
            batch_size = 2048
            all_embeddings = []
            
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                
                response = self.openai_client.embeddings.create(
                    model=self.embedding_model,
                    input=batch
                )
                
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)
            
            logger.info(f"Generated {len(all_embeddings)} embeddings in batches")
            return all_embeddings
            
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {str(e)}")
            raise ValueError(f"Failed to generate batch embeddings: {str(e)}")
    
    def get_or_create_collection(self, classroom_id: int):
        """
        Get existing collection or create new one for a classroom
        
        Args:
            classroom_id: Database ID of classroom
            
        Returns:
            ChromaDB collection object
        """
        collection_name = get_collection_name(classroom_id)
        
        try:
            collection = self.chroma_client.get_or_create_collection(
                name=collection_name,
                metadata={"classroom_id": classroom_id}
            )
            
            logger.info(f"Using collection: {collection_name}")
            return collection
            
        except Exception as e:
            logger.error(f"Error accessing collection {collection_name}: {str(e)}")
            raise
    
    def add_document_chunks(
        self,
        classroom_id: int,
        file_id: int,
        chunks: List[DocumentChunk]
    ) -> Dict[str, Any]:
        """
        Add document chunks to vector store with embeddings
        
        Args:
            classroom_id: Classroom the file belongs to
            file_id: Database ID of file
            chunks: List of DocumentChunk objects
            
        Returns:
            Dictionary with processing stats
        """
        try:
            collection = self.get_or_create_collection(classroom_id)
            
            # Prepare data for ChromaDB
            ids = []
            documents = []
            metadatas = []
            
            for chunk in chunks:
                # Generate unique ID: file_id + chunk_index
                chunk_id = f"file_{file_id}_chunk_{chunk.chunk_index}"
                
                # Prepare metadata
                metadata = {
                    "file_id": file_id,
                    "chunk_index": chunk.chunk_index,
                    "page_number": chunk.page_number or -1,
                    "slide_number": chunk.slide_number or -1,
                    **chunk.metadata
                }
                
                ids.append(chunk_id)
                documents.append(chunk.content)
                metadatas.append(metadata)
            
            # Generate embeddings for all chunks (batch)
            logger.info(f"Generating embeddings for {len(chunks)} chunks...")
            embeddings = self.generate_embeddings_batch(documents)
            
            # Add to ChromaDB
            collection.add(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas
            )
            
            logger.info(f"Added {len(chunks)} chunks to collection {get_collection_name(classroom_id)}")
            
            return {
                "success": True,
                "chunks_added": len(chunks),
                "collection_name": get_collection_name(classroom_id),
                "file_id": file_id
            }
            
        except Exception as e:
            logger.error(f"Error adding chunks to vector store: {str(e)}")
            raise ValueError(f"Failed to add chunks: {str(e)}")
    
    def search_similar_chunks(
        self,
        classroom_id: int,
        query: str,
        file_id: Optional[int] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search for chunks similar to query using semantic search
        
        Args:
            classroom_id: Classroom to search in
            query: Search query text
            file_id: Optional filter by specific file
            top_k: Number of results to return
            
        Returns:
            List of matching chunks with metadata and similarity scores
        """
        try:
            collection = self.get_or_create_collection(classroom_id)
            
            # Generate embedding for query
            query_embedding = self.generate_embedding(query)
            
            # Prepare filter
            where_filter = None
            if file_id is not None:
                where_filter = {"file_id": file_id}
            
            # Search in ChromaDB
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_filter
            )
            
            # Format results
            formatted_results = []
            for i in range(len(results['ids'][0])):
                formatted_results.append({
                    "id": results['ids'][0][i],
                    "content": results['documents'][0][i],
                    "metadata": results['metadatas'][0][i],
                    "distance": results['distances'][0][i] if 'distances' in results else None
                })
            
            logger.info(f"Found {len(formatted_results)} similar chunks for query")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error searching vector store: {str(e)}")
            raise ValueError(f"Failed to search: {str(e)}")
    
    def delete_file_chunks(self, classroom_id: int, file_id: int) -> bool:
        """
        Delete all chunks for a specific file
        
        Args:
            classroom_id: Classroom ID
            file_id: File ID to delete
            
        Returns:
            True if successful
        """
        try:
            collection = self.get_or_create_collection(classroom_id)
            
            # Delete all chunks with this file_id
            collection.delete(
                where={"file_id": file_id}
            )
            
            logger.info(f"Deleted chunks for file {file_id} from collection")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting file chunks: {str(e)}")
            return False
    
    def delete_collection(self, classroom_id: int) -> bool:
        """
        Delete entire collection for a classroom
        
        Args:
            classroom_id: Classroom ID
            
        Returns:
            True if successful
        """
        try:
            collection_name = get_collection_name(classroom_id)
            self.chroma_client.delete_collection(name=collection_name)
            
            logger.info(f"Deleted collection: {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting collection: {str(e)}")
            return False
    
    def get_collection_stats(self, classroom_id: int) -> Dict[str, Any]:
        """
        Get statistics about a classroom's collection
        
        Args:
            classroom_id: Classroom ID
            
        Returns:
            Dictionary with collection stats
        """
        try:
            collection = self.get_or_create_collection(classroom_id)
            count = collection.count()
            
            return {
                "collection_name": get_collection_name(classroom_id),
                "total_chunks": count,
                "classroom_id": classroom_id
            }
            
        except Exception as e:
            logger.error(f"Error getting collection stats: {str(e)}")
            return {}


# Singleton instance
vector_store = VectorStore()