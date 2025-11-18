"""
Document Processing Service
Extracts text from PDF, DOCX, PPTX, and TXT files
Chunks text intelligently for embedding generation
"""

import os
import io
import logging
from typing import List, Dict, Optional
from pathlib import Path

# PDF processing
from PyPDF2 import PdfReader

# DOCX processing
from docx import Document as DocxDocument

# PPTX processing
from pptx import Presentation

# Token counting
import tiktoken

logger = logging.getLogger(__name__)


class DocumentChunk:
    """Represents a chunk of text from a document"""
    def __init__(
        self,
        content: str,
        chunk_index: int,
        page_number: Optional[int] = None,
        slide_number: Optional[int] = None,
        metadata: Optional[Dict] = None
    ):
        self.content = content
        self.chunk_index = chunk_index
        self.page_number = page_number
        self.slide_number = slide_number
        self.metadata = metadata or {}

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        return {
            "content": self.content,
            "chunk_index": self.chunk_index,
            "page_number": self.page_number,
            "slide_number": self.slide_number,
            "metadata": self.metadata
        }


class DocumentProcessor:
    """
    Processes documents and extracts text with intelligent chunking
    """
    
    def __init__(
        self,
        chunk_size: int = 800,  # tokens per chunk
        chunk_overlap: int = 200,  # overlap between chunks
        encoding_name: str = "cl100k_base"  # OpenAI's encoding
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.encoding = tiktoken.get_encoding(encoding_name)
        
    def count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken"""
        return len(self.encoding.encode(text))
    
    def extract_text_from_pdf(self, file_content: bytes) -> List[Dict[str, any]]:
        """
        Extract text from PDF file
        
        Args:
            file_content: PDF file as bytes
            
        Returns:
            List of dictionaries with page_number and text
        """
        try:
            pdf_file = io.BytesIO(file_content)
            pdf_reader = PdfReader(pdf_file)
            
            pages = []
            for page_num, page in enumerate(pdf_reader.pages, start=1):
                text = page.extract_text()
                if text.strip():  # Only include non-empty pages
                    pages.append({
                        "page_number": page_num,
                        "text": text.strip()
                    })
            
            logger.info(f"Extracted text from {len(pages)} PDF pages")
            return pages
            
        except Exception as e:
            logger.error(f"Error extracting PDF text: {str(e)}")
            raise ValueError(f"Failed to extract text from PDF: {str(e)}")
    
    def extract_text_from_docx(self, file_content: bytes) -> List[Dict[str, any]]:
        """
        Extract text from DOCX file
        
        Args:
            file_content: DOCX file as bytes
            
        Returns:
            List of dictionaries with paragraph text
        """
        try:
            docx_file = io.BytesIO(file_content)
            doc = DocxDocument(docx_file)
            
            # DOCX doesn't have pages, treat each paragraph as a section
            paragraphs = []
            for idx, para in enumerate(doc.paragraphs, start=1):
                text = para.text.strip()
                if text:  # Only include non-empty paragraphs
                    paragraphs.append({
                        "page_number": None,  # DOCX doesn't have page numbers
                        "paragraph_index": idx,
                        "text": text
                    })
            
            logger.info(f"Extracted {len(paragraphs)} paragraphs from DOCX")
            return paragraphs
            
        except Exception as e:
            logger.error(f"Error extracting DOCX text: {str(e)}")
            raise ValueError(f"Failed to extract text from DOCX: {str(e)}")
    
    def extract_text_from_pptx(self, file_content: bytes) -> List[Dict[str, any]]:
        """
        Extract text from PPTX file
        
        Args:
            file_content: PPTX file as bytes
            
        Returns:
            List of dictionaries with slide_number and text
        """
        try:
            pptx_file = io.BytesIO(file_content)
            prs = Presentation(pptx_file)
            
            slides = []
            for slide_num, slide in enumerate(prs.slides, start=1):
                slide_text = []
                
                # Extract text from all shapes in slide
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        text = shape.text.strip()
                        if text:
                            slide_text.append(text)
                
                if slide_text:  # Only include slides with text
                    slides.append({
                        "slide_number": slide_num,
                        "text": "\n".join(slide_text)
                    })
            
            logger.info(f"Extracted text from {len(slides)} PPTX slides")
            return slides
            
        except Exception as e:
            logger.error(f"Error extracting PPTX text: {str(e)}")
            raise ValueError(f"Failed to extract text from PPTX: {str(e)}")
    
    def extract_text_from_txt(self, file_content: bytes) -> List[Dict[str, any]]:
        """
        Extract text from TXT file
        
        Args:
            file_content: TXT file as bytes
            
        Returns:
            List with single dictionary containing all text
        """
        try:
            text = file_content.decode('utf-8', errors='ignore').strip()
            
            if not text:
                raise ValueError("TXT file is empty")
            
            return [{
                "page_number": None,
                "text": text
            }]
            
        except Exception as e:
            logger.error(f"Error extracting TXT text: {str(e)}")
            raise ValueError(f"Failed to extract text from TXT: {str(e)}")
    
    def extract_text(self, file_content: bytes, file_type: str) -> List[Dict[str, any]]:
        """
        Extract text from file based on type
        
        Args:
            file_content: File content as bytes
            file_type: File extension (pdf, docx, pptx, txt)
            
        Returns:
            List of text sections with metadata
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
        
        return extractors[file_type](file_content)
    
    def chunk_text(
        self,
        text_sections: List[Dict[str, any]],
        file_type: str
    ) -> List[DocumentChunk]:
        """
        Chunk extracted text intelligently
        
        Strategy:
        - Respects natural boundaries (pages, slides, paragraphs)
        - Maintains context with overlap
        - Tracks metadata (page/slide numbers)
        
        Args:
            text_sections: Output from extract_text()
            file_type: File extension for metadata
            
        Returns:
            List of DocumentChunk objects
        """
        chunks = []
        chunk_index = 0
        
        for section in text_sections:
            text = section['text']
            page_num = section.get('page_number')
            slide_num = section.get('slide_number')
            
            # Split text into sentences (simple approach)
            sentences = text.replace('\n', ' ').split('. ')
            
            current_chunk = []
            current_tokens = 0
            
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                
                sentence_tokens = self.count_tokens(sentence)
                
                # If adding this sentence exceeds chunk_size, save current chunk
                if current_tokens + sentence_tokens > self.chunk_size and current_chunk:
                    chunk_text = '. '.join(current_chunk) + '.'
                    
                    chunks.append(DocumentChunk(
                        content=chunk_text,
                        chunk_index=chunk_index,
                        page_number=page_num,
                        slide_number=slide_num,
                        metadata={
                            'file_type': file_type,
                            'token_count': current_tokens
                        }
                    ))
                    
                    chunk_index += 1
                    
                    # Start new chunk with overlap
                    # Keep last few sentences for context
                    overlap_sentences = current_chunk[-2:] if len(current_chunk) > 2 else current_chunk
                    current_chunk = overlap_sentences + [sentence]
                    current_tokens = sum(self.count_tokens(s) for s in current_chunk)
                else:
                    current_chunk.append(sentence)
                    current_tokens += sentence_tokens
            
            # Add remaining chunk if any
            if current_chunk:
                chunk_text = '. '.join(current_chunk) + '.'
                chunks.append(DocumentChunk(
                    content=chunk_text,
                    chunk_index=chunk_index,
                    page_number=page_num,
                    slide_number=slide_num,
                    metadata={
                        'file_type': file_type,
                        'token_count': current_tokens
                    }
                ))
                chunk_index += 1
        
        logger.info(f"Created {len(chunks)} chunks from {len(text_sections)} sections")
        return chunks
    
    def process_document(
        self,
        file_content: bytes,
        filename: str
    ) -> List[DocumentChunk]:
        """
        Main processing pipeline: extract text → chunk → return chunks
        
        Args:
            file_content: File bytes
            filename: Original filename (to determine type)
            
        Returns:
            List of DocumentChunk objects ready for embedding
        """
        # Get file extension
        file_type = Path(filename).suffix.lower().strip('.')
        
        logger.info(f"Processing {filename} (type: {file_type})")
        
        # Step 1: Extract text
        text_sections = self.extract_text(file_content, file_type)
        
        if not text_sections:
            raise ValueError(f"No text extracted from {filename}")
        
        # Step 2: Chunk text
        chunks = self.chunk_text(text_sections, file_type)
        
        if not chunks:
            raise ValueError(f"No chunks created from {filename}")
        
        logger.info(f"Successfully processed {filename}: {len(chunks)} chunks")
        return chunks


# Singleton instance
document_processor = DocumentProcessor(
    chunk_size=800,      # ~800 tokens per chunk
    chunk_overlap=200    # 200 token overlap for context
)