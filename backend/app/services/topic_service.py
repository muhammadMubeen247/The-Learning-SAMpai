"""
Topic Service
Handles database operations for topics
"""

import logging
from typing import List, Dict
from sqlalchemy.orm import Session

from app.models.topic import Topic

logger = logging.getLogger(__name__)


def save_topics_to_db(
    db: Session,
    file_id: int,
    topics_data: List[Dict[str, any]]
) -> List[Topic]:
    """
    Save extracted topics to database
    
    Args:
        db: Database session
        file_id: ID of the file these topics belong to
        topics_data: List of topic dictionaries from extractor
        
    Returns:
        List of created Topic objects
    """
    try:
        created_topics = []
        
        for topic_data in topics_data:
            topic = Topic(
                file_id=file_id,
                topic_name=topic_data["topic"],
                introduction=topic_data.get("introduction", ""),
                order=topic_data.get("order", 0)
            )
            
            db.add(topic)
            created_topics.append(topic)
        
        db.commit()
        
        # Refresh to get IDs
        for topic in created_topics:
            db.refresh(topic)
        
        logger.info(f"Saved {len(created_topics)} topics for file {file_id}")
        
        return created_topics
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving topics to database: {str(e)}")
        raise


def get_topics_by_file(db: Session, file_id: int) -> List[Topic]:
    """
    Get all topics for a file
    
    Args:
        db: Database session
        file_id: File ID
        
    Returns:
        List of Topic objects ordered by order field
    """
    return db.query(Topic).filter(
        Topic.file_id == file_id
    ).order_by(Topic.order).all()


def delete_topics_by_file(db: Session, file_id: int) -> bool:
    """
    Delete all topics for a file
    
    Args:
        db: Database session
        file_id: File ID
        
    Returns:
        True if successful
    """
    try:
        db.query(Topic).filter(Topic.file_id == file_id).delete()
        db.commit()
        logger.info(f"Deleted topics for file {file_id}")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting topics: {str(e)}")
        return False