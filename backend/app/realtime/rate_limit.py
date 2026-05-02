import time
import os
from typing import Optional


async def check_message_rate(user_id: int, thread_id: int, redis=None) -> bool:
    """Max 10 messages per 10 seconds per (user, thread). Sliding window via Redis sorted set."""
    if redis is None:
        return True  # No Redis — skip rate limiting
    key = f"rl:msg:{user_id}:{thread_id}"
    now = time.time()
    window = 10.0
    async with redis.pipeline() as pipe:
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, int(window) + 1)
        results = await pipe.execute()
    count = results[2]
    return count <= 10


async def check_agent_rate(user_id: int, thread_id: int, redis=None) -> bool:
    """Max 3 @SAMpai invocations per 60 seconds per (user, thread)."""
    if redis is None:
        return True
    key = f"rl:agent:{user_id}:{thread_id}"
    now = time.time()
    window = 60.0
    async with redis.pipeline() as pipe:
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, int(window) + 1)
        results = await pipe.execute()
    count = results[2]
    return count <= 3
