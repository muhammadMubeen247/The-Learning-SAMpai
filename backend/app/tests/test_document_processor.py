"""
Test document processor
Run: pytest app/tests/test_document_processor.py
"""

import pytest
from app.services.document_processor import document_processor

def test_token_counting():
    """Test token counting works"""
    text = "Hello, world! This is a test."
    token_count = document_processor.count_tokens(text)
    assert token_count > 0
    print(f"✓ Token count: {token_count}")


def test_pdf_extraction():
    """Test PDF text extraction (requires a sample PDF)"""
    # You would need to provide a sample PDF file for this
    # For now, just verify the method exists
    assert hasattr(document_processor, 'extract_text_from_pdf')
    print("✓ PDF extraction method exists")


def test_chunking():
    """Test text chunking"""
    # Sample text sections
    text_sections = [{
        "page_number": 1,
        "text": "This is a test. " * 200  # Long text to trigger chunking
    }]
    
    chunks = document_processor.chunk_text(text_sections, 'txt')
    
    assert len(chunks) > 0
    assert chunks[0].content != ""
    assert chunks[0].chunk_index == 0
    
    print(f"Created {len(chunks)} chunks")
    print(f"First chunk: {chunks[0].content[:100]}...")


if __name__ == "__main__":
    test_token_counting()
    test_pdf_extraction()
    test_chunking()
    print("\n All document processor tests passed!")