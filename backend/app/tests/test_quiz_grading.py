"""Unit tests for quiz grading — no external dependencies."""
import pytest
from app.services.quiz_service import grade_attempt


MCQ_QUESTIONS = [
    {"id": 1, "type": "mcq", "prompt": "Q1", "options": ["A", "B", "C", "D"], "answer": 2, "explanation": ""},
    {"id": 2, "type": "mcq", "prompt": "Q2", "options": ["A", "B", "C", "D"], "answer": 0, "explanation": ""},
    {"id": 3, "type": "tf",  "prompt": "Q3", "answer": True,  "explanation": ""},
    {"id": 4, "type": "tf",  "prompt": "Q4", "answer": False, "explanation": ""},
]


def test_all_correct():
    answers = [
        {"question_id": 1, "answer": 2},
        {"question_id": 2, "answer": 0},
        {"question_id": 3, "answer": True},
        {"question_id": 4, "answer": False},
    ]
    result = grade_attempt(MCQ_QUESTIONS, answers)
    assert result["score"] == 1.0
    assert result["correct_count"] == 4
    assert result["total_count"] == 4
    assert all(row["correct"] for row in result["answers_full"])


def test_all_wrong():
    answers = [
        {"question_id": 1, "answer": 0},
        {"question_id": 2, "answer": 3},
        {"question_id": 3, "answer": False},
        {"question_id": 4, "answer": True},
    ]
    result = grade_attempt(MCQ_QUESTIONS, answers)
    assert result["score"] == 0.0
    assert result["correct_count"] == 0
    assert not any(row["correct"] for row in result["answers_full"])


def test_partial_correct():
    answers = [
        {"question_id": 1, "answer": 2},   # correct
        {"question_id": 2, "answer": 3},   # wrong
        {"question_id": 3, "answer": True}, # correct
        {"question_id": 4, "answer": True}, # wrong
    ]
    result = grade_attempt(MCQ_QUESTIONS, answers)
    assert result["correct_count"] == 2
    assert result["score"] == pytest.approx(0.5)


def test_missing_answers_count_as_wrong():
    answers = [
        {"question_id": 1, "answer": 2},  # correct
    ]
    result = grade_attempt(MCQ_QUESTIONS, answers)
    assert result["correct_count"] == 1
    assert result["total_count"] == 4
    assert result["score"] == pytest.approx(0.25)


def test_tf_string_coercion():
    questions = [{"id": 1, "type": "tf", "prompt": "X", "answer": True, "explanation": ""}]
    # Backend receives bool from JSON, but test with string to verify coercion path
    result = grade_attempt(questions, [{"question_id": 1, "answer": "true"}])
    assert result["correct_count"] == 1


def test_empty_questions():
    result = grade_attempt([], [])
    assert result["score"] == 0.0
    assert result["total_count"] == 0
