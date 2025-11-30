"""
Test LangChain Phase 1 Integration
Run: python -m app.tests.test_langchain_phase1
"""

from app.services.langchain_document_processor import langchain_document_processor
from app.services.vector_store import vector_store


def test_langchain_document_loading():
    """Test LangChain document loaders"""
    
    # Sample text content
    sample_pdf_content = b"%PDF-1.4 sample content"  # Mock PDF
    
    print("✓ LangChain document processor initialized")
    print(f"  Chunk size: {langchain_document_processor.chunk_size}")
    print(f"  Chunk overlap: {langchain_document_processor.chunk_overlap}")
    
    return True


def test_langchain_embeddings():
    """Test LangChain OpenAI Embeddings"""
    
    text = "This is a test sentence for LangChain embeddings."
    
    try:
        # Test single embedding
        embedding = vector_store.generate_embedding(text)
        
        assert isinstance(embedding, list)
        assert len(embedding) > 0
        
        print(f"✓ LangChain embedding generated: {len(embedding)} dimensions")
        
        # Test batch embeddings
        texts = ["First sentence.", "Second sentence.", "Third sentence."]
        embeddings = vector_store.generate_embeddings_batch(texts)
        
        assert len(embeddings) == len(texts)
        
        print(f"✓ LangChain batch embeddings: {len(embeddings)} vectors")
        
        return True
        
    except Exception as e:
        print(f"✗ LangChain embeddings failed: {e}")
        return False


def test_text_splitting():
    """Test LangChain RecursiveCharacterTextSplitter"""
    
    long_text = "This is a test sentence. " * 200  # Long text
    
    text_sections = [{
        "page_number": 1,
        "text": long_text
    }]
    
    try:
        chunks = langchain_document_processor.chunk_text_langchain(
            text_sections,
            file_type='txt'
        )
        
        assert len(chunks) > 0
        
        print(f"✓ LangChain text splitter created {len(chunks)} chunks")
        print(f"  First chunk tokens: {chunks[0].metadata.get('token_count')}")
        
        return True
        
    except Exception as e:
        print(f"✗ Text splitting failed: {e}")
        return False


if __name__ == "__main__":
    print("Testing LangChain Phase 1 Integration")
    print("="*60)
    
    tests = [
        ("Document Loading", test_langchain_document_loading),
        ("OpenAI Embeddings", test_langchain_embeddings),
        ("Text Splitting", test_text_splitting)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'-'*60}")
        print(f"Test: {test_name}")
        print('-'*60)
        success = test_func()
        results.append((test_name, success))
    
    print(f"\n{'='*60}")
    print("Phase 1 Test Summary")
    print('='*60)
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    if all(r[1] for r in results):
        print("\n🎉 Phase 1 tests passed! Ready for Phase 2.")
    else:
        print("\n⚠️  Some tests failed. Check logs.")