import asyncio
import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class ConnMeta:
    user_id: int
    kind: str  # "thread" | "user"
    thread_id: int | None = None


class ConnectionManager:
    def __init__(self):
        self._thread_rooms: dict[int, set[WebSocket]] = defaultdict(set)
        self._user_sockets: dict[int, set[WebSocket]] = defaultdict(set)
        self._meta: dict[WebSocket, ConnMeta] = {}
        self._fanout = os.getenv("WS_FANOUT", "memory")
        self._redis = None
        self._sub_task = None

    async def start(self, redis=None):
        if self._fanout == "redis" and redis:
            self._redis = redis
            self._sub_task = asyncio.create_task(self._subscriber_loop())
        logger.info(f"connection_manager: ready (fanout={self._fanout})")

    async def stop(self):
        if self._sub_task:
            self._sub_task.cancel()

    async def register_thread(self, ws: WebSocket, thread_id: int, user_id: int):
        self._thread_rooms[thread_id].add(ws)
        self._meta[ws] = ConnMeta(user_id=user_id, kind="thread", thread_id=thread_id)
        if self._fanout == "redis" and self._redis:
            await self._redis.subscribe(f"gc:thread:{thread_id}")

    async def register_user(self, ws: WebSocket, user_id: int):
        self._user_sockets[user_id].add(ws)
        self._meta[ws] = ConnMeta(user_id=user_id, kind="user")
        if self._fanout == "redis" and self._redis:
            await self._redis.subscribe(f"gc:user:{user_id}")

    async def disconnect(self, ws: WebSocket):
        meta = self._meta.pop(ws, None)
        if meta is None:
            return
        if meta.kind == "thread" and meta.thread_id is not None:
            self._thread_rooms[meta.thread_id].discard(ws)
            if not self._thread_rooms[meta.thread_id]:
                del self._thread_rooms[meta.thread_id]
        elif meta.kind == "user":
            self._user_sockets[meta.user_id].discard(ws)
            if not self._user_sockets[meta.user_id]:
                del self._user_sockets[meta.user_id]

    async def broadcast_thread(
        self, thread_id: int, event: Any, exclude: WebSocket | None = None
    ):
        payload = json.dumps(
            event.model_dump() if hasattr(event, "model_dump") else event
        )
        if self._fanout == "redis" and self._redis:
            await self._redis.publish(f"gc:thread:{thread_id}", payload)
        else:
            await self._broadcast_local_thread(thread_id, payload, exclude)

    async def _broadcast_local_thread(
        self, thread_id: int, payload: str, exclude: WebSocket | None
    ):
        dead = set()
        for ws in list(self._thread_rooms.get(thread_id, set())):
            if ws is exclude:
                continue
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        for ws in dead:
            await self.disconnect(ws)

    async def send_to_user(self, user_id: int, event: Any):
        payload = json.dumps(
            event.model_dump() if hasattr(event, "model_dump") else event
        )
        if self._fanout == "redis" and self._redis:
            await self._redis.publish(f"gc:user:{user_id}", payload)
        else:
            dead = set()
            for ws in list(self._user_sockets.get(user_id, set())):
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.add(ws)
            for ws in dead:
                await self.disconnect(ws)

    def presence_for_thread(self, thread_id: int) -> list[int]:
        return list(
            {
                self._meta[ws].user_id
                for ws in self._thread_rooms.get(thread_id, set())
                if ws in self._meta
            }
        )

    async def _subscriber_loop(self):
        # Redis pub/sub fan-out — only relevant in multi-worker mode (WS_FANOUT=redis)
        pubsub = self._redis.pubsub()
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                channel = message["channel"]
                payload = message["data"]
                if channel.startswith("gc:thread:"):
                    thread_id = int(channel.split(":")[-1])
                    await self._broadcast_local_thread(thread_id, payload, exclude=None)
                elif channel.startswith("gc:user:"):
                    user_id = int(channel.split(":")[-1])
                    for ws in list(self._user_sockets.get(user_id, set())):
                        try:
                            await ws.send_text(payload)
                        except Exception:
                            await self.disconnect(ws)
        except asyncio.CancelledError:
            await pubsub.close()
