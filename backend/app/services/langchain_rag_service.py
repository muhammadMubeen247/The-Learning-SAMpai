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
        template = """You are an intelligent educational assistant helping students learn from their course materials.

Context from course materials:
{context}

Conversation history:
{chat_history}

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
- Be encouraging and supportive in your tone

Student Question: {question}

Answer:"""
        
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
            template="""Given the following conversation and a follow up question, rephrase the follow up question to be a standalone question.

Chat History:
{chat_history}

Follow Up Question: {question}

Standalone Question:"""
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