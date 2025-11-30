"""
LangChain RAG Service
Uses ConversationalRetrievalChain for RAG with memory
"""

import logging
from typing import Dict, Optional
from sqlalchemy.orm import Session

# LangChain imports - FIXED
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate

from app.config.chroma_config import OPENAI_API_KEY
from app.services.langchain_vector_store import langchain_vector_store
from app.services.langchain_memory import DatabaseChatMessageHistory

logger = logging.getLogger(__name__)


class LangChainRAGService:
    """
    RAG service using LangChain's ConversationalRetrievalChain
    Integrates vector search, LLM, and database-backed memory
    """
    
    def __init__(
        self,
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.7,
        max_tokens: int = 500
    ):
        """
        Initialize LangChain RAG service
        
        Args:
            model: OpenAI chat model
            temperature: Response randomness (0-1)
            max_tokens: Maximum response length
        """
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        # Initialize ChatOpenAI
        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            openai_api_key=OPENAI_API_KEY
        )
        
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        logger.info(f"LangChainRAGService initialized")
        logger.info(f"  Model: {model}")
        logger.info(f"  Temperature: {temperature}")
    
    def _create_system_prompt_template(self) -> PromptTemplate:
        """
        Create custom prompt template for the RAG chain
        
        Returns:
            PromptTemplate for the chain
        """
        template = """You are an intelligent, friendly educational assistant helping students learn from their course materials. Your goal is to have natural, engaging conversations while teaching effectively.

Context from course materials:
{context}

Conversation history:
{chat_history}

Your communication style:
- Respond naturally as if you're a helpful tutor having a real conversation
- When answering follow-up questions, acknowledge what was discussed previously (e.g., "Building on what we just covered..." or "As I mentioned earlier...")
- Use conversational transitions like "Great question!", "Let me explain that further", "To add to that..."
- Vary your sentence structure and avoid being robotic or repetitive
- Show enthusiasm for the student's learning journey

Your educational approach:
- Answer questions based ONLY on the provided context from course documents
- Be clear, concise, but warm and encouraging in your responses
- Break down complex concepts into digestible parts
- Use analogies, examples, or real-world applications from the context when helpful
- If the context doesn't contain enough information, say something like: "Based on the materials we have, I don't see information about that specific topic. However, I can help you with [related topic from context]."
- Encourage critical thinking by occasionally asking reflective questions (but always provide the answer too)

For follow-up questions specifically:
- Reference the previous exchange naturally (e.g., "Remember when we talked about X? Well, Y is similar because...")
- Build upon previous answers rather than repeating information
- Use pronouns and context clues (like "this", "that concept", "as we discussed") to maintain conversation flow
- If the student asks for clarification, rephrase using simpler terms or different examples

Citation and accuracy:
- Don't make up information not in the context
- When referencing specific information, you can mention it comes from the course materials
- Be honest about limitations: if something isn't covered in the materials, acknowledge it kindly
- Stay focused on the course content rather than going off on tangents

Tone guidelines:
- Be supportive and encouraging, especially when students struggle
- Celebrate understanding: "Exactly!" or "You've got it!"
- Show patience: "Let me explain that differently..." or "No problem, let's break this down..."
- Be professional but personable—like a favorite teacher, not a textbook

Student Question: {question}

Your response (remember to be natural, conversational, and educational):"""
        
        return PromptTemplate(
            input_variables=["context", "chat_history", "question"],
            template=template
        )
    
    def create_chain_for_topic(
        self,
        classroom_id: int,
        topic_id: int,
        user_id: int,
        db: Session,
        file_id: Optional[int] = None
    ) -> ConversationalRetrievalChain:
        """
        Create a ConversationalRetrievalChain for a specific topic
        
        Args:
            classroom_id: Classroom context
            topic_id: Topic for conversation
            user_id: User having the conversation
            db: Database session
            file_id: Optional file filter
            
        Returns:
            Configured ConversationalRetrievalChain
        """
        # Get LangChain Chroma collection
        chroma = langchain_vector_store.get_chroma_collection(classroom_id)
        
        # Create retriever with optional file filter
        if file_id is not None:
            retriever = chroma.as_retriever(
                search_kwargs={
                    "k": 5,
                    "filter": {"file_id": file_id}
                }
            )
        else:
            retriever = chroma.as_retriever(
                search_kwargs={"k": 5}
            )
        
        # Create database-backed memory
        message_history = DatabaseChatMessageHistory(
            topic_id=topic_id,
            user_id=user_id,
            db=db
        )
        
        # Create ConversationBufferMemory with database backend
        memory = ConversationBufferMemory(
            chat_memory=message_history,
            memory_key="chat_history",
            return_messages=True,
            output_key="answer"
        )
        
        # Create custom condense question prompt
        condense_question_prompt = PromptTemplate(
            input_variables=["chat_history", "question"],
            template="""Given the conversation history and a follow up question, rephrase the follow up question to be a standalone question that captures all necessary context.
Important:
- If the question uses pronouns (it, that, this, they, etc.), replace them with the actual subjects from the conversation
- If the question asks for clarification or examples about a previous topic, make the topic explicit
- Preserve the original intent and scope of the question
- Keep it as a question, not a statement

Conversation History:
{chat_history}

Follow Up Question: {question}

Standalone Question (with full context):"""
        )
        
        # Create the chain
        chain = ConversationalRetrievalChain.from_llm(
            llm=self.llm,
            retriever=retriever,
            memory=memory,
            condense_question_prompt=condense_question_prompt,
            return_source_documents=True,
            verbose=True  # Enable logging
        )
        
        logger.info(f"Created ConversationalRetrievalChain for topic {topic_id}")
        
        return chain
    
    def ask_question(
        self,
        classroom_id: int,
        topic_id: int,
        user_id: int,
        question: str,
        db: Session,
        file_id: Optional[int] = None
    ) -> Dict:
        """
        Ask a question using the RAG chain
        
        Args:
            classroom_id: Classroom context
            topic_id: Topic for conversation
            user_id: User asking question
            question: User's question
            db: Database session
            file_id: Optional file filter
            
        Returns:
            Dictionary with answer, sources, and metadata
        """
        try:
            logger.info(f"[LangChain RAG] Processing question for topic {topic_id}")
            
            # Create chain for this topic
            chain = self.create_chain_for_topic(
                classroom_id=classroom_id,
                topic_id=topic_id,
                user_id=user_id,
                db=db,
                file_id=file_id
            )
            
            # Run the chain
            logger.debug(f"Running ConversationalRetrievalChain...")
            result = chain({"question": question})
            
            # Extract answer and sources
            answer = result["answer"]
            source_documents = result.get("source_documents", [])
            
            # Format sources
            sources = []
            for doc in source_documents[:3]:  # Top 3 sources
                metadata = doc.metadata
                sources.append({
                    "file_id": metadata.get("file_id"),
                    "page_number": metadata.get("page_number"),
                    "slide_number": metadata.get("slide_number"),
                    "content_preview": doc.page_content[:150] + "..."
                })
            
            # Calculate confidence based on number of sources
            confidence = "high" if len(source_documents) >= 3 else "medium" if len(source_documents) >= 1 else "low"
            
            logger.info(f"[LangChain RAG] Answer generated (confidence: {confidence})")
            
            # Note: Messages are automatically saved to database via DatabaseChatMessageHistory
            
            return {
                "answer": answer,
                "sources": sources,
                "confidence": confidence,
                "chunks_used": len(source_documents)
            }
            
        except Exception as e:
            logger.error(f"Error in LangChain RAG chain: {str(e)}", exc_info=True)
            raise ValueError(f"Failed to answer question: {str(e)}")


# Singleton instance
langchain_rag_service = LangChainRAGService(
    model="gpt-3.5-turbo",
    temperature=0.7,
    max_tokens=500
)