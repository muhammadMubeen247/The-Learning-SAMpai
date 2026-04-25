from app.database.base import Base
from app.database.session import async_engine
from app.models import user, classroom, folder, file, chat_message, quiz  # noqa: F401 — registers tables


async def init_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
