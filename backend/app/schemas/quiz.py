from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional, Union

from pydantic import BaseModel

Difficulty = Literal["easy", "medium", "hard"]
QuestionType = Literal["mcq", "tf"]
QuizStatusLit = Literal["pending", "generating", "ready", "failed", "submitted"]


# ---------------------------------------------------------------------------
# Request shapes
# ---------------------------------------------------------------------------

class GenerateQuizRequest(BaseModel):
    num_questions: Literal[5, 10, 15] = 10
    difficulty: Optional[Difficulty] = None


class SubmitAnswer(BaseModel):
    question_id: int
    answer: Union[int, bool]


class SubmitQuizRequest(BaseModel):
    answers: list[SubmitAnswer]


# ---------------------------------------------------------------------------
# Response shapes
# ---------------------------------------------------------------------------

class GenerateQuizResponse(BaseModel):
    quiz_id: int
    status: QuizStatusLit


class QuestionPublic(BaseModel):
    id: int
    type: QuestionType
    prompt: str
    options: Optional[list[str]] = None


class AnswerReview(BaseModel):
    question_id: int
    type: QuestionType
    prompt: str
    options: Optional[list[str]] = None
    user_answer: Optional[Union[int, bool]] = None
    correct_answer: Union[int, bool]
    correct: bool
    explanation: str


class AttemptResult(BaseModel):
    attempt_id: int
    quiz_id: int
    score: float
    correct_count: int
    total_count: int
    submitted_at: datetime
    review: list[AnswerReview]


class QuizDetail(BaseModel):
    quiz_id: int
    status: QuizStatusLit
    difficulty: Difficulty
    difficulty_source: str
    num_questions: int
    created_at: datetime
    ready_at: Optional[datetime] = None
    questions: Optional[list[QuestionPublic]] = None
    attempt: Optional[AttemptResult] = None
    error_msg: Optional[str] = None


class QuizHistoryItem(BaseModel):
    quiz_id: int
    difficulty: Difficulty
    num_questions: int
    score: Optional[float] = None
    correct_count: Optional[int] = None
    submitted_at: Optional[datetime] = None
    created_at: datetime
    status: QuizStatusLit


class QuizHistoryResponse(BaseModel):
    items: list[QuizHistoryItem]
    has_open_quiz: bool
    open_quiz_id: Optional[int] = None
