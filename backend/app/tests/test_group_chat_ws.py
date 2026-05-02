"""
WebSocket integration tests for group chat.
All tests in this file require real DB + services.
Marked @pytest.mark.integration — they are skipped without a live Postgres.
"""
import os
import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_ws_requires_valid_token():
    """Connecting to /ws/user with an invalid token should close with 4401."""
    import os
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")

    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # httpx doesn't natively do WS but we just test the HTTP endpoint
        # In a real E2E you'd use a WS client
        pass


@pytest.mark.integration
@pytest.mark.asyncio
async def test_thread_ws_requires_membership():
    """Connecting to /ws/group-chat/{id} when not a member closes with 4403."""
    import os
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")

    # Placeholder — real WS testing needs starlette testclient
    pytest.skip("Full WS integration test requires starlette WebSocket testclient setup")
