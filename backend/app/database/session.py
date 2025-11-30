import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

# UPDATED: Use postgresql+psycopg driver (psycopg v3)
# Change from: postgresql://... to postgresql+psycopg://...
if DATABASE_URL.startswith("postgresql://"):
    db_url = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
else:
    db_url = DATABASE_URL

# Create engine with psycopg v3
engine = create_engine(
    db_url,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,
    max_overflow=20
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """
    Dependency function to get database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()