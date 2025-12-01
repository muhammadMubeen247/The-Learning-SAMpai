"""
RAG (Retrieval-Augmented Generation) Service
Implements question-answering using document embeddings and GPT
NOW USING: LangChain vector store
"""

import logging
from typing import List, Dict, Optional
from openai import OpenAI

from app.config.chroma_config import OPENAI_API_KEY

# OLD: from app.services.vector_store import vector_store
# NEW: LangChain vector store
from app.services.langchain_vector_store import langchain_vector_store

logger = logging.getLogger(__name__)


class RAGService:
    """
    Handles RAG-based question answering
    NOW USING: LangChain vector store for retrieval
    """
    
    def __init__(
        self,
        model: str = "gpt-5-mini-2025-08-07",
        temperature: float = 0.7,
        max_tokens: int = 500
    ):
        """Initialize RAG service"""
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # Use LangChain vector store
        self.vector_store = langchain_vector_store
        
        logger.info(f"RAGService initialized with LangChain vector store")
        logger.info(f"  Model: {model}")
    
    def _create_system_prompt(self) -> str:
        """Create system prompt for the AI assistant"""
        return """You are an intelligent educational assistant helping students learn from their course materials.

Your role:
- Answer questions based ONLY on the provided context from course documents
- Be clear, concise, and educational in your responses
- If the context doesn't contain enough information to answer, say so honestly
- Use examples from the context when helpful
- Encourage deeper understanding, not just memorization

Guidelines:
- Don't make up information not in the context
- Cite specific parts of the material when relevant
- If asked about topics not in the context, politely redirect to the available material
- Be encouraging and supportive in your tone"""
    
    def _create_user_prompt(
        self,
        question: str,
        context_chunks: List[Dict],
        chat_history: Optional[List[Dict]] = None
    ) -> str:
        """Create user prompt with context and question"""
        # Format context from retrieved chunks
        context_text = "\n\n".join([
            f"[Source {i+1}]:\n{chunk['content']}"
            for i, chunk in enumerate(context_chunks)
        ])
        
        # Build prompt
        prompt_parts = []
        
        # Add context
        prompt_parts.append("CONTEXT FROM COURSE MATERIALS:")
        prompt_parts.append(context_text)
        prompt_parts.append("\n" + "="*60 + "\n")
        
        # Add chat history if exists
        if chat_history and len(chat_history) > 0:
            prompt_parts.append("CONVERSATION HISTORY:")
            for msg in chat_history[-5:]:  # Last 5 messages
                role = "Student" if msg["role"] == "user" else "Assistant"
                prompt_parts.append(f"{role}: {msg['content']}")
            prompt_parts.append("\n" + "="*60 + "\n")
        
        # Add current question
        prompt_parts.append("STUDENT QUESTION:")
        prompt_parts.append(question)
        prompt_parts.append("\nPlease answer based on the context provided above.")
        
        return "\n".join(prompt_parts)
    
    def ask_question(
        self,
        classroom_id: int,
        question: str,
        file_id: Optional[int] = None,
        chat_history: Optional[List[Dict]] = None,
        top_k: int = 5
    ) -> Dict:
        """
        Answer a question using RAG with LangChain vector store
        
        Args:
            classroom_id: Classroom context
            question: User's question
            file_id: Optional - limit search to specific file
            chat_history: Previous conversation messages
            top_k: Number of relevant chunks to retrieve
            
        Returns:
            Dictionary with answer, sources, and metadata
        """
        try:
            logger.info(f"[LangChain RAG] Processing question for classroom {classroom_id}")
            
            # Step 1: Retrieve relevant chunks using LangChain Chroma
            logger.debug(f"Searching LangChain Chroma (top_k={top_k})")
            context_chunks = self.vector_store.search_similar_chunks(
                classroom_id=classroom_id,
                query=question,
                file_id=file_id,
                top_k=top_k
            )
            
            if not context_chunks:
                return {
                    "answer": "I couldn't find any relevant information in the course materials to answer your question. Could you please rephrase or ask about a different topic?",
                    "sources": [],
                    "confidence": "low"
                }
            
            logger.info(f"[LangChain] Retrieved {len(context_chunks)} relevant chunks")
            
            # Step 2: Create prompts
            system_prompt = self._create_system_prompt()
            user_prompt = self._create_user_prompt(
                question=question,
                context_chunks=context_chunks,
                chat_history=chat_history
            )
            
            # Step 3: Call GPT for answer
            logger.debug("Calling OpenAI API for answer generation")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            answer = response.choices[0].message.content
            
            # Step 4: Extract source information
            sources = []
            for chunk in context_chunks[:3]:  # Top 3 sources
                metadata = chunk.get('metadata', {})
                sources.append({
                    "file_id": metadata.get('file_id'),
                    "page_number": metadata.get('page_number'),
                    "slide_number": metadata.get('slide_number'),
                    "content_preview": chunk['content'][:150] + "..."
                })
            
            # Calculate confidence based on similarity scores
            avg_distance = sum(
                chunk.get('distance', 1.0) for chunk in context_chunks
            ) / len(context_chunks)
            
            confidence = "high" if avg_distance < 0.3 else "medium" if avg_distance < 0.5 else "low"
            
            logger.info(f"[LangChain RAG] Answer generated (confidence: {confidence})")
            
            return {
                "answer": answer,
                "sources": sources,
                "confidence": confidence,
                "chunks_used": len(context_chunks)
            }
            
        except Exception as e:
            logger.error(f"Error in LangChain RAG: {str(e)}", exc_info=True)
            raise ValueError(f"Failed to answer question: {str(e)}")


# Singleton instance
rag_service = RAGService(
    model="gpt-5-mini-2025-08-07",
    temperature=0.7,
    max_tokens=500
)











#OLD CODE


# """
# RAG (Retrieval-Augmented Generation) Service
# Implements question-answering using document embeddings and GPT
# """

# import logging
# from typing import List, Dict, Optional
# from openai import OpenAI

# from app.config.chroma_config import OPENAI_API_KEY
# from app.services.vector_store import vector_store

# logger = logging.getLogger(__name__)


# class RAGService:
#     """
#     Handles RAG-based question answering
#     """
    
#     def __init__(
#         self,
#         model: str = "gpt-5-mini-2025-08-07",
#         temperature: float = 0.7,
#         max_tokens: int = 500
#     ):
#         """
#         Initialize RAG service
        
#         Args:
#             model: OpenAI chat model to use
#             temperature: Response randomness (0-1)
#             max_tokens: Maximum response length
#         """
#         if not OPENAI_API_KEY:
#             raise ValueError("OPENAI_API_KEY not found in environment variables")
        
#         self.client = OpenAI(api_key=OPENAI_API_KEY)
#         self.model = model
#         self.temperature = temperature
#         self.max_tokens = max_tokens
        
#         logger.info(f"RAGService initialized with model: {model}")
    
#     def _create_system_prompt(self) -> str:
#         """
#         Create system prompt for the AI assistant
        
#         Returns:
#             System prompt string
#         """
#         return """You are an intelligent educational assistant helping students learn from their course materials.

# Your role:
# - Answer questions based ONLY on the provided context from course documents
# - Be clear, concise, and educational in your responses
# - If the context doesn't contain enough information to answer, say so honestly
# - Use examples from the context when helpful
# - Encourage deeper understanding, not just memorization

# Guidelines:
# - Don't make up information not in the context
# - Cite specific parts of the material when relevant
# - If asked about topics not in the context, politely redirect to the available material
# - Be encouraging and supportive in your tone"""
    
#     def _create_user_prompt(
#         self,
#         question: str,
#         context_chunks: List[Dict],
#         chat_history: Optional[List[Dict]] = None
#     ) -> str:
#         """
#         Create user prompt with context and question
        
#         Args:
#             question: User's question
#             context_chunks: Relevant document chunks
#             chat_history: Previous messages in conversation
            
#         Returns:
#             Formatted prompt string
#         """
#         # Format context from retrieved chunks
#         context_text = "\n\n".join([
#             f"[Source {i+1}]:\n{chunk['content']}"
#             for i, chunk in enumerate(context_chunks)
#         ])
        
#         # Build prompt
#         prompt_parts = []
        
#         # Add context
#         prompt_parts.append("CONTEXT FROM COURSE MATERIALS:")
#         prompt_parts.append(context_text)
#         prompt_parts.append("\n" + "="*60 + "\n")
        
#         # Add chat history if exists
#         if chat_history and len(chat_history) > 0:
#             prompt_parts.append("CONVERSATION HISTORY:")
#             for msg in chat_history[-5:]:  # Last 5 messages for context
#                 role = "Student" if msg["role"] == "user" else "Assistant"
#                 prompt_parts.append(f"{role}: {msg['content']}")
#             prompt_parts.append("\n" + "="*60 + "\n")
        
#         # Add current question
#         prompt_parts.append("STUDENT QUESTION:")
#         prompt_parts.append(question)
#         prompt_parts.append("\nPlease answer based on the context provided above.")
        
#         return "\n".join(prompt_parts)
    
#     def ask_question(
#         self,
#         classroom_id: int,
#         question: str,
#         file_id: Optional[int] = None,
#         chat_history: Optional[List[Dict]] = None,
#         top_k: int = 5
#     ) -> Dict:
#         """
#         Answer a question using RAG
        
#         Args:
#             classroom_id: Classroom context
#             question: User's question
#             file_id: Optional - limit search to specific file
#             chat_history: Previous conversation messages
#             top_k: Number of relevant chunks to retrieve
            
#         Returns:
#             Dictionary with answer, sources, and metadata
#         """
#         try:
#             logger.info(f"Processing question for classroom {classroom_id}")
            
#             # Step 1: Retrieve relevant chunks from vector store
#             logger.debug(f"Searching for relevant chunks (top_k={top_k})")
#             context_chunks = vector_store.search_similar_chunks(
#                 classroom_id=classroom_id,
#                 query=question,
#                 file_id=file_id,
#                 top_k=top_k
#             )
            
#             if not context_chunks:
#                 return {
#                     "answer": "I couldn't find any relevant information in the course materials to answer your question. Could you please rephrase or ask about a different topic?",
#                     "sources": [],
#                     "confidence": "low"
#                 }
            
#             logger.info(f"Retrieved {len(context_chunks)} relevant chunks")
            
#             # Step 2: Create prompts
#             system_prompt = self._create_system_prompt()
#             user_prompt = self._create_user_prompt(
#                 question=question,
#                 context_chunks=context_chunks,
#                 chat_history=chat_history
#             )
            
#             # Step 3: Call GPT for answer
#             logger.debug("Calling OpenAI API for answer generation")
#             response = self.client.chat.completions.create(
#                 model=self.model,
#                 messages=[
#                     {"role": "system", "content": system_prompt},
#                     {"role": "user", "content": user_prompt}
#                 ],
#                 temperature=self.temperature,
#                 max_tokens=self.max_tokens
#             )
            
#             answer = response.choices[0].message.content
            
#             # Step 4: Extract source information
#             sources = []
#             for chunk in context_chunks[:3]:  # Top 3 sources
#                 metadata = chunk.get('metadata', {})
#                 sources.append({
#                     "file_id": metadata.get('file_id'),
#                     "page_number": metadata.get('page_number'),
#                     "slide_number": metadata.get('slide_number'),
#                     "content_preview": chunk['content'][:150] + "..."
#                 })
            
#             # Calculate confidence based on similarity scores
#             avg_distance = sum(
#                 chunk.get('distance', 1.0) for chunk in context_chunks
#             ) / len(context_chunks)
            
#             confidence = "high" if avg_distance < 0.3 else "medium" if avg_distance < 0.5 else "low"
            
#             logger.info(f"Answer generated successfully (confidence: {confidence})")
            
#             return {
#                 "answer": answer,
#                 "sources": sources,
#                 "confidence": confidence,
#                 "chunks_used": len(context_chunks)
#             }
            
#         except Exception as e:
#             logger.error(f"Error in RAG question answering: {str(e)}", exc_info=True)
#             raise ValueError(f"Failed to answer question: {str(e)}")


# # Singleton instance
# rag_service = RAGService(
#     model="gpt-5-mini-2025-08-07",
#     temperature=0.7,
#     max_tokens=500
# )