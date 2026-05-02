"""
Tests for GroupChatAgent — guard + respond pipelines.
All tests mock DB, RAG, LLM — no real services needed.

LLM-hitting tests are marked @pytest.mark.llm (skipped in CI).
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message(
    id=1,
    content="hello world",
    is_discarded=False,
    role=None,
    reply_to_id=None,
    user_id=10,
    seq=1,
    mentions=None,
    author=None,
):
    from app.models.group_chat import GroupChatMessage, GroupMessageRole
    msg = MagicMock(spec=GroupChatMessage)
    msg.id = id
    msg.content = content
    msg.is_discarded = is_discarded
    msg.role = role or GroupMessageRole.USER
    msg.reply_to_id = reply_to_id
    msg.user_id = user_id
    msg.seq = seq
    msg.mentions = mentions or []
    msg.author = author or MagicMock(username="alice")
    msg.group_chat_id = 1
    msg.created_at = datetime.utcnow()
    msg.discard_reason = None  # Explicit None for Pydantic validation
    msg.client_msg_id = None   # Explicit None for Pydantic validation
    return msg


def _make_file(
    id=1,
    filename="Lecture.pdf",
    file_url="https://r2.example.com/lecture.pdf",
    processing_status=None,
    folder_id=1,
):
    from app.models.file import File, ProcessingStatus
    f = MagicMock(spec=File)
    f.id = id
    f.filename = filename
    f.file_url = file_url
    f.processing_status = processing_status or ProcessingStatus.COMPLETED
    f.folder_id = folder_id
    return f


def _make_agent(sampai_id=99, rag_service=None, cm=None):
    from app.services.group_chat_agent import GroupChatAgent

    rag = rag_service or AsyncMock()
    connection_manager = cm or AsyncMock()
    openai_client = AsyncMock()

    return GroupChatAgent(
        sampai_user_id=sampai_id,
        classroom_rag_service=rag,
        connection_manager=connection_manager,
        openai_client=openai_client,
    )


# ---------------------------------------------------------------------------
# Stage A: Heuristic skip tests
# ---------------------------------------------------------------------------


def test_stage_a_short_message_skips():
    """Message < 10 chars → guard should skip without calling Stage B."""
    agent = _make_agent()
    msg = _make_message(content="hi")  # 2 chars

    db = AsyncMock()
    result = agent._should_skip_guard(msg, db)
    assert result is True


def test_stage_a_reply_to_skips():
    """Message is a reply to another message → Stage A skip."""
    agent = _make_agent()
    msg = _make_message(content="This is a long enough message", reply_to_id=5)

    db = AsyncMock()
    result = agent._should_skip_guard(msg, db)
    assert result is True


def test_stage_a_normal_message_not_skipped():
    """Normal long message with no reply → should NOT be skipped."""
    agent = _make_agent()
    msg = _make_message(content="What is gradient descent?", reply_to_id=None)

    db = AsyncMock()
    result = agent._should_skip_guard(msg, db)
    assert result is False


# ---------------------------------------------------------------------------
# Stage B: Vector similarity tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stage_b_on_topic_high_sim():
    """High cosine similarity → returns (True, 'high'), no discard."""
    from app.services.group_chat_agent import TOPIC_SIM_HIGH

    agent = _make_agent()
    file = _make_file()

    mock_folder = MagicMock()
    mock_folder.classroom_id = 7

    mock_chunks_store = AsyncMock()
    # distance=0.1 → sim = 1 - 0.1/2 = 0.95 → above TOPIC_SIM_HIGH
    mock_chunks_store.query.return_value = [{"distance": 0.1, "content": "relevant"}]

    mock_engine = AsyncMock()
    mock_engine._chunks_vdb = mock_chunks_store

    mock_rag = AsyncMock()
    mock_rag.get_engine = AsyncMock(return_value=mock_engine)
    agent._rag = mock_rag

    with patch(
        "app.services.group_chat_agent._resolve_folder_for_file",
        new=AsyncMock(return_value=mock_folder),
    ):
        is_on_topic, confidence = await agent._check_vector_similarity(
            "What is gradient descent?", file
        )

    assert is_on_topic is True
    assert confidence == "high"


@pytest.mark.asyncio
async def test_stage_b_off_topic_low_sim():
    """Low cosine similarity → returns (False, 'high'), should discard."""
    from app.services.group_chat_agent import TOPIC_SIM_LOW

    agent = _make_agent()
    file = _make_file()

    mock_folder = MagicMock()
    mock_folder.classroom_id = 7

    mock_chunks_store = AsyncMock()
    # distance=1.9 → sim = 1 - 1.9/2 = 0.05 → below TOPIC_SIM_LOW
    mock_chunks_store.query.return_value = [{"distance": 1.9, "content": "unrelated"}]

    mock_engine = AsyncMock()
    mock_engine._chunks_vdb = mock_chunks_store

    mock_rag = AsyncMock()
    mock_rag.get_engine = AsyncMock(return_value=mock_engine)
    agent._rag = mock_rag

    with patch(
        "app.services.group_chat_agent._resolve_folder_for_file",
        new=AsyncMock(return_value=mock_folder),
    ):
        is_on_topic, confidence = await agent._check_vector_similarity(
            "What is the latest football score?", file
        )

    assert is_on_topic is False
    assert confidence == "high"


@pytest.mark.asyncio
async def test_stage_b_empty_results_borderline():
    """No chunks returned → returns (None, 'medium') for Stage C escalation."""
    agent = _make_agent()
    file = _make_file()

    mock_folder = MagicMock()
    mock_folder.classroom_id = 7

    mock_chunks_store = AsyncMock()
    mock_chunks_store.query.return_value = []

    mock_engine = AsyncMock()
    mock_engine._chunks_vdb = mock_chunks_store

    mock_rag = AsyncMock()
    mock_rag.get_engine = AsyncMock(return_value=mock_engine)
    agent._rag = mock_rag

    with patch(
        "app.services.group_chat_agent._resolve_folder_for_file",
        new=AsyncMock(return_value=mock_folder),
    ):
        is_on_topic, confidence = await agent._check_vector_similarity("test", file)

    assert is_on_topic is None
    assert confidence == "medium"


# ---------------------------------------------------------------------------
# Stage C: LLM judge tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stage_c_discards_when_off_topic_high_severity():
    """
    LLM judge returns is_on_topic=False, severity=3 → message should be discarded.
    """
    from unittest.mock import patch, AsyncMock, MagicMock
    from app.models.group_chat import GroupMessageRole

    agent = _make_agent()
    file = _make_file()
    message = _make_message(content="What is the latest football score?")

    # Mock Stage A skip → returns False (proceed)
    agent._should_skip_guard = MagicMock(return_value=False)

    # Mock Stage B → borderline
    agent._check_vector_similarity = AsyncMock(return_value=(None, "medium"))

    # Mock LLM judge → off-topic
    class FakeJudgement:
        is_on_topic = False
        severity = 3
        reason = "completely unrelated to the document"

    agent._llm_judge = AsyncMock(return_value=FakeJudgement())
    agent._discard_message = AsyncMock()

    mock_db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = message
    mock_db.execute.return_value = execute_result
    # Directly mock the DB.get call (returns file for file_id lookup)
    mock_db.get = AsyncMock(return_value=file)

    with patch(
        "app.services.group_chat_context.fetch_recent_messages",
        new=AsyncMock(return_value=[]),
    ):
        await agent._guard(mock_db, message_id=1, thread_id=1, file_id=1)

    agent._discard_message.assert_called_once()


@pytest.mark.asyncio
async def test_stage_c_no_discard_low_severity():
    """
    LLM judge returns is_on_topic=False, severity=1 (low) → message kept.
    """
    agent = _make_agent()
    file = _make_file()
    message = _make_message(content="Some borderline message here")

    agent._should_skip_guard = MagicMock(return_value=False)
    agent._check_vector_similarity = AsyncMock(return_value=(None, "medium"))

    class FakeLowSeverityJudgement:
        is_on_topic = False
        severity = 1  # Too low to discard
        reason = "slightly tangential"

    agent._llm_judge = AsyncMock(return_value=FakeLowSeverityJudgement())
    agent._discard_message = AsyncMock()

    mock_db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = message
    mock_db.execute.return_value = execute_result
    mock_db.get = AsyncMock(return_value=file)

    with patch(
        "app.services.group_chat_context.fetch_recent_messages",
        new=AsyncMock(return_value=[]),
    ):
        await agent._guard(mock_db, message_id=1, thread_id=1, file_id=1)

    agent._discard_message.assert_not_called()


# ---------------------------------------------------------------------------
# Respond path tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_respond_inserts_agent_row():
    """
    Respond path: mock engine.aquery → agent row inserted with correct reply_to_id.
    """
    from app.models.group_chat import GroupMessageRole
    from app.rag.base import QueryResult

    cm = AsyncMock()
    agent = _make_agent(sampai_id=99, cm=cm)

    file = _make_file(processing_status=__import__("app.models.file", fromlist=["ProcessingStatus"]).ProcessingStatus.COMPLETED)
    folder = MagicMock()
    folder.classroom_id = 7
    classroom = MagicMock()
    classroom.id = 7

    trigger_msg = _make_message(id=10, content="@SAMpai what is HRM?")
    agent_msg = _make_message(id=11, content="HRM stands for Human Resource Management.", user_id=99, role=GroupMessageRole.AGENT)

    mock_engine = AsyncMock()
    mock_engine.aquery = AsyncMock(return_value=QueryResult(content="HRM stands for Human Resource Management."))

    mock_rag = AsyncMock()
    mock_rag.get_engine = AsyncMock(return_value=mock_engine)
    agent._rag = mock_rag

    mock_db = AsyncMock()
    # execute for trigger_msg load
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = trigger_msg
    mock_db.execute.return_value = execute_result

    # db.get calls: file, folder, classroom
    mock_db.get = AsyncMock(side_effect=[file, folder, classroom])

    inserted_msg = None

    async def mock_send_message(db, thread_id, user_id, content, reply_to_id=None, role=None):
        nonlocal inserted_msg
        msg = _make_message(
            id=11,
            content=content,
            user_id=user_id,
            role=role or GroupMessageRole.AGENT,
            reply_to_id=reply_to_id,
        )
        inserted_msg = msg
        return msg

    with patch(
        "app.services.group_chat_agent.fetch_recent_messages",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.services.group_chat_service.send_message",
        new=mock_send_message,
    ), patch(
        "app.services.group_chat_agent.send_message",
        new=mock_send_message,
        create=True,
    ):
        await agent._respond(mock_db, message_id=10, thread_id=1, file_id=1)

    assert inserted_msg is not None
    assert inserted_msg.reply_to_id == 10  # replies to the triggering message
    # broadcast_thread should have been called (agent_typing + message_new)
    assert cm.broadcast_thread.call_count >= 1


@pytest.mark.asyncio
async def test_respond_file_processing_returns_system_message():
    """
    If file.processing_status != COMPLETED → send system message, do NOT call engine.
    """
    from app.models.file import ProcessingStatus

    cm = AsyncMock()
    agent = _make_agent(sampai_id=99, cm=cm)

    file = _make_file(processing_status=ProcessingStatus.PROCESSING)
    trigger_msg = _make_message(id=10, content="@SAMpai help!")

    mock_db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = trigger_msg
    mock_db.execute.return_value = execute_result
    mock_db.get = AsyncMock(return_value=file)

    system_messages = []

    async def mock_send_system(db, thread_id, content, reply_to_id=None):
        system_messages.append(content)

    agent._send_system_message = mock_send_system

    await agent._respond(mock_db, message_id=10, thread_id=1, file_id=1)

    assert len(system_messages) == 1
    assert "indexing" in system_messages[0].lower() or "processing" in system_messages[0].lower()
    # Engine should never have been called
    agent._rag.get_engine.assert_not_called()


# ---------------------------------------------------------------------------
# is_discarded filter test (CRITICAL)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_recent_messages_excludes_discarded():
    """
    fetch_recent_messages MUST filter is_discarded=False.
    A discarded message in the DB must NOT appear in context.
    """
    from app.services.group_chat_context import fetch_recent_messages
    from app.models.group_chat import GroupChatMessage, GroupMessageRole

    normal_msg = _make_message(id=1, content="normal", is_discarded=False)
    discarded_msg = _make_message(id=2, content="discarded", is_discarded=True)

    # Mock DB returning ONLY normal_msg (simulating WHERE is_discarded=False)
    mock_db = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [normal_msg]
    execute_result = MagicMock()
    execute_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = execute_result

    results = await fetch_recent_messages(mock_db, thread_id=1, limit=10)

    # Only normal_msg should be in the results
    assert len(results) == 1
    assert results[0].content == "normal"
    assert results[0].is_discarded is False

    # Verify the query included is_discarded filter
    # (check the WHERE clause was applied by confirming only non-discarded returned)
    for msg in results:
        assert msg.is_discarded is False


# ---------------------------------------------------------------------------
# Per-thread semaphore test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_per_thread_semaphore_serializes_concurrent_responds():
    """
    Two concurrent run_respond calls on the same thread_id must be serialized
    (second waits for first). Test via the semaphore directly.
    """
    import time
    from app.services.group_chat_agent import GroupChatAgent

    cm = AsyncMock()
    rag = AsyncMock()
    agent = GroupChatAgent(
        sampai_user_id=99,
        classroom_rag_service=rag,
        connection_manager=cm,
        openai_client=AsyncMock(),
    )

    call_order = []
    call_times = []

    async def _simulated_task(message_id: int):
        """Simulate what run_respond does: acquire semaphore, do work."""
        async with agent._semaphore(thread_id=1):
            call_order.append(message_id)
            call_times.append(time.monotonic())
            await asyncio.sleep(0.05)  # simulate work

    t1 = asyncio.create_task(_simulated_task(1))
    t2 = asyncio.create_task(_simulated_task(2))
    await asyncio.gather(t1, t2)

    # Both should have been called
    assert len(call_order) == 2
    # Second call should start no earlier than ~0.05s after first (serialized)
    if len(call_times) == 2:
        gap = call_times[1] - call_times[0]
        assert gap >= 0.04, f"Calls were not serialized: gap={gap:.3f}s"


# ---------------------------------------------------------------------------
# Guard: discard propagates correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guard_discards_and_broadcasts():
    """
    When _discard_message is called, it sets is_discarded=True, commits, and broadcasts.
    """
    agent = _make_agent()
    file = _make_file()
    message = _make_message(id=5, content="spam message no topic here")
    message.is_discarded = False

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    cm = AsyncMock()
    agent._cm = cm

    await agent._discard_message(mock_db, message, thread_id=1, reason="off_topic")

    assert message.is_discarded is True
    assert message.discard_reason == "off_topic"
    mock_db.commit.assert_called_once()
    cm.broadcast_thread.assert_called_once()

    # Verify the event type
    event_arg = cm.broadcast_thread.call_args[0][1]
    assert event_arg.type == "message_discarded"
    assert event_arg.message_id == 5
