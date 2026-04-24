import os

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

# Convert any psycopg/psycopg2 URL scheme to asyncpg — asyncpg is the only
# working Postgres driver available in this environment.
asyncpg_url = (
    DATABASE_URL
    .replace("postgresql+psycopg://", "postgresql+asyncpg://")
    .replace("postgresql+psycopg2://", "postgresql+asyncpg://")
)
if asyncpg_url.startswith("postgresql://"):
    asyncpg_url = asyncpg_url.replace("postgresql://", "postgresql+asyncpg://", 1)

async_engine = create_async_engine(
    asyncpg_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

# Exposed for Alembic env.py (sync migrations only — do not use in app code)
engine = async_engine.sync_engine

Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
