"""
Test vector store service
Run: python -m app.tests.test_vector_store
"""

from app.services.vector_store import vector_store
from app.services.document_processor import DocumentChunk

def test_embedding_generation():
    """Test OpenAI embedding generation"""
    text = "This is a test sentence for embedding generation."
    
    try:
        embedding = vector_store.generate_embedding(text)
        
        assert isinstance(embedding, list)
        assert len(embedding) > 0
        assert all(isinstance(x, float) for x in embedding)
        
        print(f"✓ Generated embedding with {len(embedding)} dimensions")
        return True
        
    except Exception as e:
        print(f"✗ Embedding generation failed: {e}")
        return False


def test_batch_embedding():
    """Test batch embedding generation"""
    texts = [
        "First test sentence.",
        "Second test sentence.",
        "Third test sentence."
    ]
    
    try:
        embeddings = vector_store.generate_embeddings_batch(texts)
        
        assert len(embeddings) == len(texts)
        assert all(isinstance(emb, list) for emb in embeddings)
        
        print(f"✓ Generated {len(embeddings)} batch embeddings")
        return True
        
    except Exception as e:
        print(f"✗ Batch embedding failed: {e}")
        return False


def test_collection_operations():
    """Test ChromaDB collection creation"""
    classroom_id = 999  # Test classroom
    
    try:
        # Get or create collection
        collection = vector_store.get_or_create_collection(classroom_id)
        
        assert collection is not None
        
        # Get stats
        stats = vector_store.get_collection_stats(classroom_id)
        
        assert "collection_name" in stats
        assert stats["classroom_id"] == classroom_id
        
        print(f"✓ Collection operations work")
        print(f"  Collection: {stats['collection_name']}")
        print(f"  Total chunks: {stats['total_chunks']}")
        
        # Clean up test collection
        vector_store.delete_collection(classroom_id)
        print(f"✓ Cleaned up test collection")
        
        return True
        
    except Exception as e:
        print(f"✗ Collection operations failed: {e}")
        return False


def test_add_and_search():
    """Test adding chunks and searching"""
    classroom_id = 999
    file_id = 1
    
    try:
        # Create test chunks
        chunks = [
            DocumentChunk(
                content="Machine learning is a subset of artificial intelligence.",
                chunk_index=0,
                page_number=1,
                metadata={"file_type": "pdf"}
            ),
            DocumentChunk(
                content="Deep learning uses neural networks with multiple layers.",
                chunk_index=1,
                page_number=1,
                metadata={"file_type": "pdf"}
            ),
            DocumentChunk(
                content="Natural language processing helps computers understand text.",
                chunk_index=2,
                page_number=2,
                metadata={"file_type": "pdf"}
            )
        ]
        
        # Add chunks
        result = vector_store.add_document_chunks(classroom_id, file_id, chunks)
        
        assert result["success"]
        assert result["chunks_added"] == 3
        
        print(f"✓ Added {result['chunks_added']} chunks to vector store")
        
        # Search for similar chunks
        query = "What is machine learning?"
        results = vector_store.search_similar_chunks(classroom_id, query, top_k=2)
        
        assert len(results) > 0
        assert "content" in results[0]
        assert "metadata" in results[0]
        
        print(f"✓ Search returned {len(results)} results")
        print(f"  Top result: {results[0]['content'][:80]}...")
        
        # Clean up
        vector_store.delete_collection(classroom_id)
        print(f"✓ Cleaned up test data")
        
        return True
        
    except Exception as e:
        print(f"✗ Add and search failed: {e}")
        # Clean up on error
        vector_store.delete_collection(classroom_id)
        return False


if __name__ == "__main__":
    print("Testing Vector Store Service\n")
    
    tests = [
        ("Embedding Generation", test_embedding_generation),
        ("Batch Embedding", test_batch_embedding),
        ("Collection Operations", test_collection_operations),
        ("Add and Search", test_add_and_search)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*60}")
        print(f"Running: {test_name}")
        print('='*60)
        success = test_func()
        results.append((test_name, success))
    
    print(f"\n{'='*60}")
    print("Test Summary")
    print('='*60)
    for test_name, success in results:
        status = " PASS" if success else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    all_passed = all(result[1] for result in results)
    if all_passed:
        print("\n🎉 All tests passed!")
    else:
        print("\n Some tests failed. Check your OpenAI API key and configuration.")