"""
LangChain Document Processor
Uses LangChain document loaders and text splitters
"""

import logging
import io
from typing import List, Dict, Optional
from pathlib import Path

# LangChain imports
from langchain_community.document_loaders import (
    PyPDFLoader,
    Docx2txtLoader,
    UnstructuredPowerPointLoader,
    TextLoader
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document as LangChainDocument

# Keep our custom chunk class for compatibility
from app.services.document_processor import DocumentChunk
import tiktoken

logger = logging.getLogger(__name__)


class LangChainDocumentProcessor:
    """
    Document processor using LangChain abstractions
    Maintains compatibility with existing DocumentChunk schema
    """
    
    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 200,
        encoding_name: str = "cl100k_base"
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.encoding = tiktoken.get_encoding(encoding_name)
        
        # LangChain text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=self._count_tokens,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        
        logger.info("LangChain DocumentProcessor initialized")
    
    def _count_tokens(self, text: str) -> int:
        """Token counting function for text splitter"""
        return len(self.encoding.encode(text))
    
    def _save_temp_file(self, content: bytes, filename: str) -> str:
        """
        Save bytes to temporary file for LangChain loaders
        
        Args:
            content: File bytes
            filename: Original filename
            
        Returns:
            Path to temporary file
        """
        import tempfile
        
        suffix = Path(filename).suffix
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp_file.write(content)
        temp_file.close()
        
        return temp_file.name
    
    def extract_text_from_pdf(
        self,
        file_content: bytes,
        filename: str
    ) -> List[Dict[str, any]]:
        """
        Extract text from PDF using LangChain PyPDFLoader
        
        Args:
            file_content: PDF bytes
            filename: Original filename
            
        Returns:
            List of dicts with page_number and text (compatible with old format)
        """
        try:
            # Save to temp file (LangChain loaders need file paths)
            temp_path = self._save_temp_file(file_content, filename)
            
            # Load with LangChain
            loader = PyPDFLoader(temp_path)
            documents = loader.load()
            
            # Convert to our format
            pages = []
            for doc in documents:
                page_num = doc.metadata.get('page', 0) + 1  # LangChain uses 0-indexed
                pages.append({
                    "page_number": page_num,
                    "text": doc.page_content.strip()
                })
            
            # Clean up temp file
            import os
            os.unlink(temp_path)
            
            logger.info(f"[LangChain] Extracted {len(pages)} pages from PDF")
            return pages
            
        except Exception as e:
            logger.error(f"LangChain PDF extraction failed: {e}")
            # Fallback to old method
            logger.info("Falling back to PyPDF2 extraction")
            from app.services.document_processor import document_processor
            return document_processor.extract_text_from_pdf(file_content)
    
    def extract_text_from_docx(
        self,
        file_content: bytes,
        filename: str
    ) -> List[Dict[str, any]]:
        """
        Extract text from DOCX using LangChain Docx2txtLoader
        """
        try:
            temp_path = self._save_temp_file(file_content, filename)
            
            loader = Docx2txtLoader(temp_path)
            documents = loader.load()
            
            # DOCX returns single document, split into paragraphs
            paragraphs = []
            for idx, doc in enumerate(documents, 1):
                paragraphs.append({
                    "page_number": None,
                    "paragraph_index": idx,
                    "text": doc.page_content.strip()
                })
            
            import os
            os.unlink(temp_path)
            
            logger.info(f"[LangChain] Extracted {len(paragraphs)} sections from DOCX")
            return paragraphs
            
        except Exception as e:
            logger.error(f"LangChain DOCX extraction failed: {e}")
            from app.services.document_processor import document_processor
            return document_processor.extract_text_from_docx(file_content)
    
    def extract_text_from_pptx(
        self,
        file_content: bytes,
        filename: str
    ) -> List[Dict[str, any]]:
        """
        Extract text from PPTX using LangChain UnstructuredPowerPointLoader
        """
        try:
            temp_path = self._save_temp_file(file_content, filename)
            
            # Try LangChain loader
            try:
                from langchain_community.document_loaders import UnstructuredPowerPointLoader
                
                loader = UnstructuredPowerPointLoader(temp_path)
                documents = loader.load()
                
                # Process slides
                slides = []
                for idx, doc in enumerate(documents, 1):
                    slides.append({
                        "slide_number": idx,
                        "text": doc.page_content.strip()
                    })
                
                import os
                os.unlink(temp_path)
                
                logger.info(f"[LangChain] Extracted {len(slides)} slides from PPTX")
                return slides
                
            except ImportError as import_error:
                logger.warning(f"LangChain PPTX loader not available: {import_error}")
                logger.info("Falling back to python-pptx extraction")
                
                # Fallback to old method
                import os
                os.unlink(temp_path)
                from app.services.document_processor import document_processor
                return document_processor.extract_text_from_pptx(file_content)
                
        except Exception as e:
            logger.error(f"LangChain PPTX extraction failed: {e}")
            from app.services.document_processor import document_processor
            return document_processor.extract_text_from_pptx(file_content)
    
    def extract_text_from_txt(
        self,
        file_content: bytes,
        filename: str
    ) -> List[Dict[str, any]]:
        """Extract text from TXT (unchanged from old implementation)"""
        try:
            text = file_content.decode('utf-8', errors='ignore').strip()
            
            if not text:
                raise ValueError("TXT file is empty")
            
            return [{
                "page_number": None,
                "text": text
            }]
            
        except Exception as e:
            logger.error(f"TXT extraction failed: {e}")
            raise ValueError(f"Failed to extract text from TXT: {str(e)}")
    
    def extract_text(
        self,
        file_content: bytes,
        file_type: str
    ) -> List[Dict[str, any]]:
        """
        Extract text from file based on type
        (Same interface as old implementation)
        """
        file_type = file_type.lower().strip('.')
        
        extractors = {
            'pdf': self.extract_text_from_pdf,
            'docx': self.extract_text_from_docx,
            'pptx': self.extract_text_from_pptx,
            'txt': self.extract_text_from_txt
        }
        
        if file_type not in extractors:
            raise ValueError(f"Unsupported file type: {file_type}")
        
        # Pass filename to extractor
        filename = f"temp.{file_type}"
        return extractors[file_type](file_content, filename)
    
    def chunk_text_langchain(
        self,
        text_sections: List[Dict[str, any]],
        file_type: str
    ) -> List[DocumentChunk]:
        """
        Chunk text using LangChain RecursiveCharacterTextSplitter
        
        Args:
            text_sections: Extracted text sections
            file_type: File extension
            
        Returns:
            List of DocumentChunk objects (compatible with old format)
        """
        chunks = []
        chunk_index = 0
        
        for section in text_sections:
            text = section['text']
            page_num = section.get('page_number')
            slide_num = section.get('slide_number')
            
            # Create LangChain document
            langchain_doc = LangChainDocument(
                page_content=text,
                metadata={
                    'page_number': page_num,
                    'slide_number': slide_num,
                    'file_type': file_type
                }
            )
            
            # Split with LangChain
            split_docs = self.text_splitter.split_documents([langchain_doc])
            
            # Convert to our DocumentChunk format
            for doc in split_docs:
                token_count = self._count_tokens(doc.page_content)
                
                chunks.append(DocumentChunk(
                    content=doc.page_content,
                    chunk_index=chunk_index,
                    page_number=doc.metadata.get('page_number'),
                    slide_number=doc.metadata.get('slide_number'),
                    metadata={
                        'file_type': file_type,
                        'token_count': token_count
                    }
                ))
                
                chunk_index += 1
        
        logger.info(f"[LangChain] Created {len(chunks)} chunks from {len(text_sections)} sections")
        return chunks
    
    def process_document(
        self,
        file_content: bytes,
        filename: str
    ) -> List[DocumentChunk]:
        """
        Main processing pipeline using LangChain
        
        Args:
            file_content: File bytes
            filename: Original filename
            
        Returns:
            List of DocumentChunk objects
        """
        file_type = Path(filename).suffix.lower().strip('.')
        
        logger.info(f"[LangChain] Processing {filename} (type: {file_type})")
        
        # Step 1: Extract text
        text_sections = self.extract_text(file_content, file_type)
        
        if not text_sections:
            raise ValueError(f"No text extracted from {filename}")
        
        # Step 2: Chunk with LangChain
        chunks = self.chunk_text_langchain(text_sections, file_type)
        
        if not chunks:
            raise ValueError(f"No chunks created from {filename}")
        
        logger.info(f"[LangChain] Successfully processed {filename}: {len(chunks)} chunks")
        return chunks


# Singleton instance
langchain_document_processor = LangChainDocumentProcessor(
    chunk_size=800,
    chunk_overlap=200
)
