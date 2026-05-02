import os
import logging

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)
_client: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis:
    global _client
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    _client = aioredis.from_url(url, decode_responses=True)
    logger.info(f"Redis client initialized: {url}")
    return _client


async def close_redis() -> None:
    global _client
    if _client:
        await _client.aclose()
        _client = None


def get_redis() -> aioredis.Redis:
    if _client is None:
        raise RuntimeError("Redis not initialized")
    return _client
