"""
Tests for ConnectionManager — in-memory fanout only.
Redis path tests are @pytest.mark.integration (require real Redis).
"""
import asyncio
import json
import pytest


# ---------------------------------------------------------------------------
# Mock WebSocket helper
# ---------------------------------------------------------------------------

class MockWS:
    def __init__(self):
        self.sent: list[str] = []
        self._fail = False

    async def send_text(self, data: str):
        if self._fail:
            raise RuntimeError("connection closed")
        self.sent.append(data)

    def set_fail(self):
        self._fail = True


# ---------------------------------------------------------------------------
# Unit tests — in-memory fanout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_broadcast_thread_reaches_all_members():
    """broadcast_thread delivers to all sockets in the room."""
    from app.realtime.connection_manager import ConnectionManager
    from app.realtime.events import MessageNewEvent

    cm = ConnectionManager()
    await cm.start()

    ws1, ws2, ws3 = MockWS(), MockWS(), MockWS()
    await cm.register_thread(ws1, thread_id=1, user_id=10)
    await cm.register_thread(ws2, thread_id=1, user_id=11)
    await cm.register_thread(ws3, thread_id=2, user_id=12)  # different room

    event = MessageNewEvent(message={"id": 42, "content": "hello"})
    await cm.broadcast_thread(thread_id=1, event=event)

    assert len(ws1.sent) == 1
    assert len(ws2.sent) == 1
    assert len(ws3.sent) == 0  # different room — should NOT receive

    payload = json.loads(ws1.sent[0])
    assert payload["type"] == "message_new"
    assert payload["message"]["id"] == 42


@pytest.mark.asyncio
async def test_broadcast_thread_skips_exclude():
    """broadcast_thread skips the excluded WebSocket."""
    from app.realtime.connection_manager import ConnectionManager
    from app.realtime.events import MessageNewEvent

    cm = ConnectionManager()
    await cm.start()

    ws1, ws2 = MockWS(), MockWS()
    await cm.register_thread(ws1, thread_id=1, user_id=10)
    await cm.register_thread(ws2, thread_id=1, user_id=11)

    event = MessageNewEvent(message={"id": 1})
    await cm.broadcast_thread(thread_id=1, event=event, exclude=ws1)

    assert len(ws1.sent) == 0
    assert len(ws2.sent) == 1


@pytest.mark.asyncio
async def test_send_to_user_reaches_only_target_user():
    """send_to_user delivers only to the target user's sockets."""
    from app.realtime.connection_manager import ConnectionManager
    from app.realtime.events import InviteNewEvent

    cm = ConnectionManager()
    await cm.start()

    ws_u1a, ws_u1b, ws_u2 = MockWS(), MockWS(), MockWS()
    await cm.register_user(ws_u1a, user_id=1)
    await cm.register_user(ws_u1b, user_id=1)  # same user, two tabs
    await cm.register_user(ws_u2, user_id=2)

    event = InviteNewEvent(invite={"id": 99})
    await cm.send_to_user(user_id=1, event=event)

    assert len(ws_u1a.sent) == 1
    assert len(ws_u1b.sent) == 1
    assert len(ws_u2.sent) == 0


@pytest.mark.asyncio
async def test_disconnect_removes_from_thread_room():
    """disconnect cleans up thread room and meta."""
    from app.realtime.connection_manager import ConnectionManager

    cm = ConnectionManager()
    await cm.start()

    ws = MockWS()
    await cm.register_thread(ws, thread_id=5, user_id=20)
    assert 5 in cm._thread_rooms

    await cm.disconnect(ws)

    # room should be gone (empty rooms are deleted)
    assert 5 not in cm._thread_rooms
    assert ws not in cm._meta


@pytest.mark.asyncio
async def test_disconnect_removes_from_user_sockets():
    """disconnect cleans up user socket registry and meta."""
    from app.realtime.connection_manager import ConnectionManager

    cm = ConnectionManager()
    await cm.start()

    ws = MockWS()
    await cm.register_user(ws, user_id=7)
    assert 7 in cm._user_sockets

    await cm.disconnect(ws)

    assert 7 not in cm._user_sockets
    assert ws not in cm._meta


@pytest.mark.asyncio
async def test_disconnect_idempotent():
    """Calling disconnect twice does not raise."""
    from app.realtime.connection_manager import ConnectionManager

    cm = ConnectionManager()
    await cm.start()

    ws = MockWS()
    await cm.register_thread(ws, thread_id=1, user_id=1)
    await cm.disconnect(ws)
    await cm.disconnect(ws)  # second call — should be a no-op


@pytest.mark.asyncio
async def test_dead_socket_cleaned_on_broadcast():
    """A socket that raises on send_text is auto-disconnected."""
    from app.realtime.connection_manager import ConnectionManager
    from app.realtime.events import MessageNewEvent

    cm = ConnectionManager()
    await cm.start()

    ws_good = MockWS()
    ws_dead = MockWS()
    ws_dead.set_fail()

    await cm.register_thread(ws_good, thread_id=1, user_id=1)
    await cm.register_thread(ws_dead, thread_id=1, user_id=2)

    event = MessageNewEvent(message={"id": 1})
    await cm.broadcast_thread(thread_id=1, event=event)

    # good socket received; dead socket was auto-removed
    assert len(ws_good.sent) == 1
    assert ws_dead not in cm._meta


@pytest.mark.asyncio
async def test_presence_for_thread_returns_online_users():
    """presence_for_thread returns unique user_ids currently in the room."""
    from app.realtime.connection_manager import ConnectionManager

    cm = ConnectionManager()
    await cm.start()

    ws1, ws2 = MockWS(), MockWS()
    await cm.register_thread(ws1, thread_id=3, user_id=100)
    await cm.register_thread(ws2, thread_id=3, user_id=101)

    online = cm.presence_for_thread(3)
    assert set(online) == {100, 101}


@pytest.mark.asyncio
async def test_concurrent_register_disconnect_no_corruption():
    """Concurrent register + disconnect via asyncio.gather must not corrupt state."""
    from app.realtime.connection_manager import ConnectionManager

    cm = ConnectionManager()
    await cm.start()

    NUM = 50
    sockets = [MockWS() for _ in range(NUM)]

    async def _reg_and_disc(ws, i):
        await cm.register_thread(ws, thread_id=1, user_id=i)
        await cm.disconnect(ws)

    await asyncio.gather(*[_reg_and_disc(ws, i) for i, ws in enumerate(sockets)])

    # All sockets should have been cleaned up
    assert len(cm._meta) == 0


# ---------------------------------------------------------------------------
# Integration test stub — requires real Redis
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_fanout_publish_receive():
    """Redis pub/sub path: publishing to a channel reaches subscribed local sockets."""
    import os
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        pytest.skip("REDIS_URL not set — skipping Redis integration test")

    from app.realtime.redis_client import init_redis, close_redis
    from app.realtime.connection_manager import ConnectionManager
    from app.realtime.events import MessageNewEvent

    redis = await init_redis()
    try:
        cm = ConnectionManager()
        # Force redis fanout mode for this test
        import os
        os.environ["WS_FANOUT"] = "redis"
        cm._fanout = "redis"
        await cm.start(redis)

        ws = MockWS()
        await cm.register_thread(ws, thread_id=99, user_id=42)

        event = MessageNewEvent(message={"id": 7})
        await cm.broadcast_thread(thread_id=99, event=event)

        # Give the subscriber loop a tick to process
        await asyncio.sleep(0.1)

        assert len(ws.sent) >= 1
    finally:
        await cm.stop()
        await close_redis()
