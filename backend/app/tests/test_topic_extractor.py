"""
Test topic extraction service
Run: python -m app.tests.test_topic_extractor
"""

from app.services.topic_extractor import topic_extractor
from app.services.document_processor import DocumentChunk


def test_topic_extraction():
    """Test GPT-based topic extraction"""
    
    # Create sample chunks (simulating a document about machine learning)
    chunks = [
        DocumentChunk(
            content="""Machine learning is a subset of artificial intelligence that focuses on 
            building systems that can learn from data. The main goal is to create algorithms 
            that can identify patterns and make decisions with minimal human intervention.""",
            chunk_index=0,
            page_number=1
        ),
        DocumentChunk(
            content="""Supervised learning is one of the most common types of machine learning. 
            In supervised learning, the algorithm learns from labeled training data. Common 
            algorithms include linear regression, logistic regression, and decision trees.""",
            chunk_index=1,
            page_number=1
        ),
        DocumentChunk(
            content="""Unsupervised learning works with unlabeled data. The algorithm tries to 
            find hidden patterns or structures in the data. Clustering and dimensionality 
            reduction are popular unsupervised learning techniques.""",
            chunk_index=2,
            page_number=2
        ),
        DocumentChunk(
            content="""Deep learning uses neural networks with multiple layers. These networks 
            can learn hierarchical representations of data. Deep learning has achieved 
            remarkable success in image recognition, natural language processing, and game playing.""",
            chunk_index=3,
            page_number=2
        ),
        DocumentChunk(
            content="""Model evaluation is crucial in machine learning. Common metrics include 
            accuracy, precision, recall, and F1 score. Cross-validation helps ensure models 
            generalize well to new data.""",
            chunk_index=4,
            page_number=3
        )
    ]
    
    try:
        # Extract topics
        print("Extracting topics from sample document...\n")
        topics = topic_extractor.extract_topics(chunks, "machine_learning.pdf")
        
        # Validate results
        assert len(topics) > 0, "No topics extracted"
        assert all("topic" in t for t in topics), "Missing 'topic' field"
        assert all("introduction" in t for t in topics), "Missing 'introduction' field"
        
        # Display results
        print(f"✓ Successfully extracted {len(topics)} topics:\n")
        
        for i, topic in enumerate(topics, 1):
            print(f"{i}. {topic['topic']}")
            print(f"   {topic['introduction']}")
            print()
        
        return True
        
    except Exception as e:
        print(f"✗ Topic extraction failed: {e}")
        return False


def test_fallback_extraction():
    """Test fallback topic extraction"""
    
    chunks = [
        DocumentChunk(
            content="Introduction to the topic.",
            chunk_index=0,
            page_number=1
        ),
        DocumentChunk(
            content="More details about the subject matter.",
            chunk_index=1,
            page_number=2
        )
    ]
    
    try:
        # Use fallback method
        topics = topic_extractor._fallback_topic_extraction(chunks, "test.pdf")
        
        assert len(topics) > 0
        assert all("topic" in t for t in topics)
        
        print(f"✓ Fallback extraction created {len(topics)} topics")
        
        for topic in topics:
            print(f"  - {topic['topic']}: {topic['introduction'][:50]}...")
        
        return True
        
    except Exception as e:
        print(f"✗ Fallback extraction failed: {e}")
        return False


def test_empty_document():
    """Test handling of empty documents"""
    
    chunks = []
    
    try:
        topics = topic_extractor.extract_topics_with_fallback(chunks, "empty.pdf")
        
        # Should return empty list or raise error
        assert isinstance(topics, list)
        
        print("✓ Empty document handled correctly")
        return True
        
    except Exception as e:
        print(f"✓ Empty document raised expected error: {type(e).__name__}")
        return True


if __name__ == "__main__":
    print("Testing Topic Extraction Service\n")
    print("="*60)
    
    tests = [
        ("Topic Extraction (GPT)", test_topic_extraction),
        ("Fallback Extraction", test_fallback_extraction),
        ("Empty Document Handling", test_empty_document)
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
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    all_passed = all(result[1] for result in results)
    if all_passed:
        print("\n🎉 All tests passed!")
    else:
        print("\n⚠️  Some tests failed.")