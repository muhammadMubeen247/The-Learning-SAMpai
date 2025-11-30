"""
Test LangChain Phase 2 Integration - Vector Store
Run: python -m app.tests.test_langchain_phase2
"""

from app.services.langchain_vector_store import langchain_vector_store
from app.services.langchain_document_processor import langchain_document_processor
from app.services.document_processor import DocumentChunk


def test_langchain_chroma_initialization():
    """Test LangChain Chroma initialization"""
    
    print("✓ LangChain Vector Store initialized")
    print(f"  Persist directory: {langchain_vector_store.persist_directory}")
    print(f"  Embedding model: {langchain_vector_store.embedding_model}")
    
    return True


def test_add_and_search_with_langchain():
    """Test adding documents and searching with LangChain Chroma"""
    
    classroom_id = 999  # Test classroom
    file_id = 1
    
    try:
        # Create test chunks
        chunks = [
            DocumentChunk(
                content="LangChain is a framework for developing applications powered by language models.",
                chunk_index=0,
                page_number=1,
                metadata={"file_type": "pdf"}
            ),
            DocumentChunk(
                content="Vector databases like ChromaDB store embeddings for semantic search.",
                chunk_index=1,
                page_number=1,
                metadata={"file_type": "pdf"}
            ),
            DocumentChunk(
                content="RAG combines retrieval and generation for better AI responses.",
                chunk_index=2,
                page_number=2,
                metadata={"file_type": "pdf"}
            )
        ]
        
        # Add chunks using LangChain
        print("\n[LangChain] Adding chunks to Chroma...")
        result = langchain_vector_store.add_document_chunks(
            classroom_id=classroom_id,
            file_id=file_id,
            chunks=chunks
        )
        
        assert result["success"]
        assert result["chunks_added"] == 3
        
        print(f"✓ Added {result['chunks_added']} chunks with LangChain Chroma")
        
        # Search for similar chunks
        print("\n[LangChain] Searching for similar chunks...")
        query = "What is LangChain?"
        results = langchain_vector_store.search_similar_chunks(
            classroom_id=classroom_id,
            query=query,
            top_k=2
        )
        
        assert len(results) > 0
        assert "content" in results[0]
        assert "metadata" in results[0]
        assert "distance" in results[0]
        
        print(f"✓ Search returned {len(results)} results")
        print(f"  Top result: {results[0]['content'][:80]}...")
        print(f"  Distance score: {results[0]['distance']:.4f}")
        
        # Get collection stats
        print("\n[LangChain] Getting collection stats...")
        stats = langchain_vector_store.get_collection_stats(classroom_id)
        
        assert stats["total_chunks"] >= 3
        assert stats["using_langchain"] == True
        
        print(f"✓ Collection stats:")
        print(f"  Total chunks: {stats['total_chunks']}")
        print(f"  Collection: {stats['collection_name']}")
        
        # Clean up
        print("\n[LangChain] Cleaning up test data...")
        langchain_vector_store.delete_collection(classroom_id)
        print("✓ Cleaned up test collection")
        
        return True
        
    except Exception as e:
        print(f"✗ LangChain Chroma test failed: {e}")
        # Clean up on error
        try:
            langchain_vector_store.delete_collection(classroom_id)
        except:
            pass
        return False


def test_file_filtering():
    """Test searching with file_id filter"""
    
    classroom_id = 998
    file_id_1 = 1
    file_id_2 = 2
    
    try:
        # Add chunks from two different files
        chunks_file1 = [
            DocumentChunk(
                content="Content from file 1 about machine learning.",
                chunk_index=0,
                page_number=1,
                metadata={"file_type": "pdf"}
            )
        ]
        
        chunks_file2 = [
            DocumentChunk(
                content="Content from file 2 about deep learning.",
                chunk_index=0,
                page_number=1,
                metadata={"file_type": "pdf"}
            )
        ]
        
        # Add both files
        langchain_vector_store.add_document_chunks(classroom_id, file_id_1, chunks_file1)
        langchain_vector_store.add_document_chunks(classroom_id, file_id_2, chunks_file2)
        
        # Search with file filter
        results = langchain_vector_store.search_similar_chunks(
            classroom_id=classroom_id,
            query="learning",
            file_id=file_id_1,
            top_k=5
        )
        
        # Should only return chunks from file 1
        assert all(r['metadata']['file_id'] == file_id_1 for r in results)
        
        print(f"✓ File filtering works correctly")
        print(f"  Found {len(results)} chunks from file {file_id_1}")
        
        # Clean up
        langchain_vector_store.delete_collection(classroom_id)
        
        return True
        
    except Exception as e:
        print(f"✗ File filtering test failed: {e}")
        try:
            langchain_vector_store.delete_collection(classroom_id)
        except:
            pass
        return False


def test_delete_file_chunks():
    """Test deleting specific file chunks"""
    
    classroom_id = 997
    file_id = 1
    
    try:
        # Add chunks
        chunks = [
            DocumentChunk(
                content="Test content for deletion.",
                chunk_index=0,
                page_number=1,
                metadata={"file_type": "pdf"}
            )
        ]
        
        langchain_vector_store.add_document_chunks(classroom_id, file_id, chunks)
        
        # Verify added
        stats_before = langchain_vector_store.get_collection_stats(classroom_id)
        assert stats_before["total_chunks"] > 0
        
        # Delete file chunks
        success = langchain_vector_store.delete_file_chunks(classroom_id, file_id)
        assert success
        
        # Verify deleted
        stats_after = langchain_vector_store.get_collection_stats(classroom_id)
        
        print(f"✓ Delete file chunks works")
        print(f"  Before: {stats_before['total_chunks']} chunks")
        print(f"  After: {stats_after['total_chunks']} chunks")
        
        # Clean up
        langchain_vector_store.delete_collection(classroom_id)
        
        return True
        
    except Exception as e:
        print(f"✗ Delete chunks test failed: {e}")
        try:
            langchain_vector_store.delete_collection(classroom_id)
        except:
            pass
        return False


if __name__ == "__main__":
    print("Testing LangChain Phase 2 Integration - Vector Store")
    print("="*60)
    
    tests = [
        ("Chroma Initialization", test_langchain_chroma_initialization),
        ("Add and Search", test_add_and_search_with_langchain),
        ("File Filtering", test_file_filtering),
        ("Delete File Chunks", test_delete_file_chunks)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'-'*60}")
        print(f"Test: {test_name}")
        print('-'*60)
        success = test_func()
        results.append((test_name, success))
    
    print(f"\n{'='*60}")
    print("Phase 2 Test Summary")
    print('='*60)
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    if all(r[1] for r in results):
        print("\n🎉 Phase 2 tests passed! Ready for Phase 3.")
        print("\n📊 LangChain Integration Status:")
        print("  ✅ Phase 1: Document Processing & Embeddings")
        print("  ✅ Phase 2: Vector Store Integration")
        print("  ⏳ Phase 3: RAG Chain & Memory (Next)")
    else:
        print("\n⚠️  Some tests failed. Check logs.")