"""
Topic Extraction Service
Uses OpenAI GPT to analyze document content and extract main topics
"""

import logging
import json
from typing import List, Dict, Optional
from openai import OpenAI

from app.config.chroma_config import OPENAI_API_KEY
from app.services.document_processor import DocumentChunk

logger = logging.getLogger(__name__)


class TopicExtractor:
    """
    Extracts topics from document chunks using GPT
    """
    
    def __init__(
        self,
        model: str = "gpt-5-mini-2025-08-07",
        max_topics: int = 10
    ):
        """
        Initialize topic extractor
        
        Args:
            model: OpenAI model to use for extraction
            max_topics: Maximum number of topics to extract
        """
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = model
        self.max_topics = max_topics
        
        logger.info(f"TopicExtractor initialized with model: {model}")
    
    def _create_extraction_prompt(self, document_text: str) -> str:
        """
        Create prompt for GPT to extract topics
        
        Args:
            document_text: Full or summarized document text
            
        Returns:
            Formatted prompt string
        """
        prompt = f"""You are an expert educational content analyzer. Analyze the following document and extract the main topics covered.

For each topic, provide:
1. A clear, concise topic name (2-8 words)
2. A brief introduction/description (1-3 sentences) explaining what the topic covers

Important guidelines:
- Extract {self.max_topics} or fewer main topics
- Topics should be distinct and non-overlapping
- Order topics as they appear in the document
- Introductions should be informative but concise
- Use academic/professional language

Document content:
{document_text}

Respond ONLY with a valid JSON object in this exact format:
{{
  "topics": [
    {{
      "topic": "Topic Name Here",
      "introduction": "Brief description of what this topic covers.",
      "order": 1
    }},
    {{
      "topic": "Another Topic",
      "introduction": "Description of the second topic.",
      "order": 2
    }}
  ]
}}

JSON response:"""
        
        return prompt
    
    def _prepare_document_summary(self, chunks: List[DocumentChunk]) -> str:
        """
        Prepare document text for topic extraction
        
        Strategy:
        - If document is short: use full text
        - If document is long: sample from beginning, middle, and end
        
        Args:
            chunks: List of document chunks
            
        Returns:
            Text summary for analysis
        """
        # Combine all chunks
        full_text = "\n\n".join([chunk.content for chunk in chunks])
        
        # Token limit for gpt-5-mini-2025-08-07 context
        max_tokens = 12000  # Leave room for response
        
        # If text is short enough, use it all
        if len(full_text) < max_tokens * 4:  # Rough char estimate
            return full_text
        
        # For long documents, sample strategically
        chunk_count = len(chunks)
        
        # Take chunks from beginning, middle, and end
        sample_size = min(chunk_count // 3, 10)  # Max 10 chunks per section
        
        beginning = chunks[:sample_size]
        middle_start = chunk_count // 2 - sample_size // 2
        middle = chunks[middle_start:middle_start + sample_size]
        end = chunks[-sample_size:]
        
        sampled_chunks = beginning + middle + end
        sampled_text = "\n\n".join([chunk.content for chunk in sampled_chunks])
        
        logger.info(f"Document summary prepared: {len(sampled_chunks)} chunks from {chunk_count} total")
        
        return sampled_text
    
    def extract_topics(
        self,
        chunks: List[DocumentChunk],
        filename: str
    ) -> List[Dict[str, any]]:
        """
        Extract topics from document chunks using GPT
        
        Args:
            chunks: List of document chunks
            filename: Original filename (for context)
            
        Returns:
            List of topic dictionaries with topic, introduction, and order
        """
        try:
            # Prepare document summary
            document_text = self._prepare_document_summary(chunks)
            
            # Create prompt
            prompt = self._create_extraction_prompt(document_text)
            
            logger.info(f"Extracting topics from {filename}...")
            
            # Call GPT
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at analyzing educational documents and extracting main topics. Always respond with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,  # Lower temperature for more consistent output
                max_tokens=1500
            )
            
            # Extract JSON from response
            response_text = response.choices[0].message.content.strip()
            
            # Try to parse JSON
            try:
                # Remove markdown code blocks if present
                if response_text.startswith("```"):
                    response_text = response_text.split("```")[1]
                    if response_text.startswith("json"):
                        response_text = response_text[4:]
                
                result = json.loads(response_text)
                
                if "topics" not in result:
                    raise ValueError("Response missing 'topics' key")
                
                topics = result["topics"]
                
                # Validate topic structure
                for i, topic in enumerate(topics):
                    if "topic" not in topic or "introduction" not in topic:
                        raise ValueError(f"Topic {i} missing required fields")
                    
                    # Ensure order field exists
                    if "order" not in topic:
                        topic["order"] = i + 1
                
                logger.info(f"Successfully extracted {len(topics)} topics from {filename}")
                
                return topics
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.error(f"Response text: {response_text}")
                raise ValueError(f"GPT returned invalid JSON: {str(e)}")
        
        except Exception as e:
            logger.error(f"Error extracting topics: {str(e)}")
            raise ValueError(f"Failed to extract topics: {str(e)}")
    
    def extract_topics_with_fallback(
        self,
        chunks: List[DocumentChunk],
        filename: str
    ) -> List[Dict[str, any]]:
        """
        Extract topics with fallback to simple heuristic method
        
        Args:
            chunks: List of document chunks
            filename: Original filename
            
        Returns:
            List of topics (from GPT or fallback)
        """
        try:
            # Try GPT extraction first
            return self.extract_topics(chunks, filename)
            
        except Exception as e:
            logger.warning(f"GPT extraction failed, using fallback: {e}")
            
            # Fallback: Create simple topics based on document structure
            return self._fallback_topic_extraction(chunks, filename)
    
    def _fallback_topic_extraction(
        self,
        chunks: List[DocumentChunk],
        filename: str
    ) -> List[Dict[str, any]]:
        """
        Simple fallback topic extraction based on document structure
        
        Strategy:
        - Group chunks by page/slide numbers
        - Create topics for major sections
        
        Args:
            chunks: List of document chunks
            filename: Original filename
            
        Returns:
            List of basic topics
        """
        logger.info("Using fallback topic extraction")
        
        topics = []
        
        # Group by pages/slides
        page_groups = {}
        for chunk in chunks:
            page_key = chunk.page_number or chunk.slide_number or 0
            if page_key not in page_groups:
                page_groups[page_key] = []
            page_groups[page_key].append(chunk)
        
        # Create topics from page groups
        sorted_pages = sorted(page_groups.keys())
        
        for i, page_num in enumerate(sorted_pages[:self.max_topics], start=1):
            chunks_in_page = page_groups[page_num]
            
            # Use first chunk content as introduction
            intro = chunks_in_page[0].content[:200] + "..." if len(chunks_in_page[0].content) > 200 else chunks_in_page[0].content
            
            topic_name = f"Section {i}"
            if page_num > 0:
                if chunks_in_page[0].page_number:
                    topic_name = f"Page {page_num}"
                elif chunks_in_page[0].slide_number:
                    topic_name = f"Slide {page_num}"
            
            topics.append({
                "topic": topic_name,
                "introduction": intro,
                "order": i
            })
        
        logger.info(f"Fallback extraction created {len(topics)} topics")
        
        return topics


# Singleton instance
topic_extractor = TopicExtractor(
    model="gpt-5-mini-2025-08-07",
    max_topics=10
)