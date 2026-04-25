"""Unit tests for difficulty inference — mocks LLM, no DB required."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.quiz import QuizDifficulty
from app.services.quiz_service import infer_difficulty


@pytest.mark.asyncio
async def test_cold_start_returns_medium_baseline():
    db = AsyncMock()
    # No chat history
    db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
    with patch("app.services.quiz_service.get_conversation_history_for_rag", return_value=[]):
        difficulty, source = await infer_difficulty(db, file_id=1, user_id=1)
    assert difficulty == QuizDifficulty.MEDIUM
    assert source == "baseline"


@pytest.mark.asyncio
async def test_llm_returns_hard():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    with (
        patch("app.services.quiz_service.get_conversation_history_for_rag", return_value=[
            {"role": "user", "content": "how does A relate to B?"},
        ]),
        patch(
            "app.services.quiz_service.openai_llm_func",
            new_callable=AsyncMock,
            return_value='{"difficulty": "hard", "reason": "synthesis questions"}',
        ),
    ):
        difficulty, source = await infer_difficulty(db, file_id=1, user_id=1)

    assert difficulty == QuizDifficulty.HARD
    assert source == "inferred"


@pytest.mark.asyncio
async def test_malformed_llm_output_falls_back_to_baseline():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    with (
        patch("app.services.quiz_service.get_conversation_history_for_rag", return_value=[
            {"role": "user", "content": "some question"},
        ]),
        patch(
            "app.services.quiz_service.openai_llm_func",
            new_callable=AsyncMock,
            return_value="not json at all !!!",
        ),
    ):
        difficulty, source = await infer_difficulty(db, file_id=1, user_id=1)

    assert difficulty == QuizDifficulty.MEDIUM
    assert source == "baseline"


@pytest.mark.asyncio
async def test_llm_exception_falls_back_to_baseline():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    with (
        patch("app.services.quiz_service.get_conversation_history_for_rag", return_value=[
            {"role": "user", "content": "some question"},
        ]),
        patch(
            "app.services.quiz_service.openai_llm_func",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API timeout"),
        ),
    ):
        difficulty, source = await infer_difficulty(db, file_id=1, user_id=1)

    assert difficulty == QuizDifficulty.MEDIUM
    assert source == "baseline"
