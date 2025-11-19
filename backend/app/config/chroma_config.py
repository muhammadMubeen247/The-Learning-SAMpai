"""
ChromaDB Configuration
Manages persistent storage location and client settings
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ChromaDB storage directory
CHROMA_DATA_DIR = os.getenv(
    "CHROMA_DATA_DIR",
    str(Path(__file__).parent.parent.parent / "chroma_data")
)

# Ensure directory exists
Path(CHROMA_DATA_DIR).mkdir(parents=True, exist_ok=True)

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")

# Collection naming convention
def get_collection_name(classroom_id: int) -> str:
    """
    Generate ChromaDB collection name for a classroom
    
    Args:
        classroom_id: Database ID of classroom
        
    Returns:
        Collection name (e.g., "classroom_123")
    """
    return f"classroom_{classroom_id}"


# Embedding dimensions by model
EMBEDDING_DIMENSIONS = {
    "text-embedding-ada-002": 1536,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072
}