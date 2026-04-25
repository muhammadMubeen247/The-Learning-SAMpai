"""
Quiz routes — generate, poll, submit, and history.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.file import ProcessingStatus
from app.models.quiz import Quiz, QuizAttempt, QuizDifficulty, QuizStatus
from app.routes.chat import _get_file_and_classroom
from app.schemas.quiz import (
    AnswerReview,
    AttemptResult,
    GenerateQuizRequest,
    GenerateQuizResponse,
    QuizDetail,
    QuizHistoryItem,
    QuizHistoryResponse,
    QuestionPublic,
    SubmitQuizRequest,
)
from app.services import quiz_service

router = APIRouter(prefix="/quiz", tags=["Quiz"])
logger = logging.getLogger(__name__)

_OPEN_STATUSES = (QuizStatus.PENDING, QuizStatus.GENERATING, QuizStatus.READY)
_STALE_GENERATING_MINUTES = 5


# ---------------------------------------------------------------------------
# POST /quiz/files/{file_id}/generate
# ---------------------------------------------------------------------------

@router.post("/files/{file_id}/generate", response_model=GenerateQuizResponse, status_code=202)
async def generate_quiz(
    file_id: int,
    body: GenerateQuizRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    file, classroom = await _get_file_and_classroom(file_id, current_user, db)

    if file.processing_status != ProcessingStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail="File is not fully processed yet. Please wait until processing completes.",
        )

    # Check for an open quiz; abandon stale GENERATING rows older than 5 min
    result = await db.execute(
        select(Quiz)
        .where(
            Quiz.user_id == current_user.id,
            Quiz.file_id == file_id,
            Quiz.status.in_(_OPEN_STATUSES),
        )
        .order_by(Quiz.created_at.desc())
    )
    open_quiz: Quiz | None = result.scalars().first()

    if open_quiz is not None:
        stale_cutoff = datetime.utcnow() - timedelta(minutes=_STALE_GENERATING_MINUTES)
        if open_quiz.status == QuizStatus.GENERATING and open_quiz.created_at < stale_cutoff:
            open_quiz.status = QuizStatus.FAILED
            open_quiz.error_msg = "abandoned — timed out during generation"
            await db.commit()
        else:
            raise HTTPException(
                status_code=409,
                detail="You have an open quiz for this file. Submit it first.",
            )

    # Resolve difficulty
    if body.difficulty is not None:
        difficulty = QuizDifficulty(body.difficulty)
        difficulty_source = "manual"
    else:
        difficulty, difficulty_source = await quiz_service.infer_difficulty(
            db, file_id, current_user.id
        )

    # Create the quiz row
    new_quiz = Quiz(
        file_id=file_id,
        user_id=current_user.id,
        status=QuizStatus.PENDING,
        difficulty=difficulty,
        difficulty_source=difficulty_source,
        num_questions=body.num_questions,
    )
    db.add(new_quiz)
    try:
        await db.commit()
        await db.refresh(new_quiz)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="You have an open quiz for this file. Submit it first.",
        )

    background_tasks.add_task(quiz_service.generate_quiz_task, new_quiz.id)
    logger.info(
        "generate_quiz: queued quiz_id=%s file_id=%s user_id=%s difficulty=%s",
        new_quiz.id, file_id, current_user.id, difficulty.value,
    )
    return GenerateQuizResponse(quiz_id=new_quiz.id, status="pending")


# ---------------------------------------------------------------------------
# GET /quiz/{quiz_id}
# ---------------------------------------------------------------------------

@router.get("/{quiz_id}", response_model=QuizDetail)
async def get_quiz(
    quiz_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _res = await db.execute(
        select(Quiz).options(selectinload(Quiz.attempt)).where(Quiz.id == quiz_id)
    )
    quiz: Quiz | None = _res.scalar_one_or_none()
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    if quiz.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    # Access-check via file/classroom membership
    await _get_file_and_classroom(quiz.file_id, current_user, db)

    questions_public: list[QuestionPublic] | None = None
    attempt_out: AttemptResult | None = None

    if quiz.status == QuizStatus.READY and quiz.attempt is None and quiz.questions:
        questions_public = [
            QuestionPublic(
                id=q["id"],
                type=q["type"],
                prompt=q["prompt"],
                options=q.get("options"),
            )
            for q in quiz.questions
        ]

    if quiz.status == QuizStatus.SUBMITTED and quiz.attempt is not None:
        attempt = quiz.attempt
        q_map = {q["id"]: q for q in (quiz.questions or [])}
        a_map = {
            row["question_id"]: row
            for row in (attempt.answers or [])
        }
        review = []
        for q_id, q in q_map.items():
            row = a_map.get(q_id, {})
            review.append(
                AnswerReview(
                    question_id=q_id,
                    type=q["type"],
                    prompt=q["prompt"],
                    options=q.get("options"),
                    user_answer=row.get("user_answer"),
                    correct_answer=q["answer"],
                    correct=row.get("correct", False),
                    explanation=q.get("explanation", ""),
                )
            )
        attempt_out = AttemptResult(
            attempt_id=attempt.id,
            quiz_id=quiz_id,
            score=attempt.score,
            correct_count=attempt.correct_count,
            total_count=attempt.total_count,
            submitted_at=attempt.submitted_at,
            review=review,
        )

    return QuizDetail(
        quiz_id=quiz.id,
        status=quiz.status.value,
        difficulty=quiz.difficulty.value,
        difficulty_source=quiz.difficulty_source,
        num_questions=quiz.num_questions,
        created_at=quiz.created_at,
        ready_at=quiz.ready_at,
        questions=questions_public,
        attempt=attempt_out,
        error_msg=quiz.error_msg,
    )


# ---------------------------------------------------------------------------
# POST /quiz/{quiz_id}/submit
# ---------------------------------------------------------------------------

@router.post("/{quiz_id}/submit", response_model=AttemptResult)
async def submit_quiz(
    quiz_id: int,
    body: SubmitQuizRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    quiz: Quiz | None = await db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    if quiz.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    await _get_file_and_classroom(quiz.file_id, current_user, db)

    if quiz.status != QuizStatus.READY:
        if quiz.status == QuizStatus.SUBMITTED:
            raise HTTPException(status_code=400, detail="Quiz already submitted.")
        raise HTTPException(
            status_code=400,
            detail=f"Quiz is not ready for submission (current status: {quiz.status.value}).",
        )

    raw_answers = [{"question_id": a.question_id, "answer": a.answer} for a in body.answers]
    result = quiz_service.grade_attempt(quiz.questions or [], raw_answers)

    attempt = QuizAttempt(
        quiz_id=quiz.id,
        user_id=current_user.id,
        file_id=quiz.file_id,
        score=result["score"],
        correct_count=result["correct_count"],
        total_count=result["total_count"],
        answers=result["answers_full"],
    )
    db.add(attempt)
    quiz.status = QuizStatus.SUBMITTED
    await db.commit()
    await db.refresh(attempt)

    q_map = {q["id"]: q for q in (quiz.questions or [])}
    review = [
        AnswerReview(
            question_id=row["question_id"],
            type=q_map[row["question_id"]]["type"],
            prompt=q_map[row["question_id"]]["prompt"],
            options=q_map[row["question_id"]].get("options"),
            user_answer=row["user_answer"],
            correct_answer=row["correct_answer"],
            correct=row["correct"],
            explanation=q_map[row["question_id"]].get("explanation", ""),
        )
        for row in result["answers_full"]
        if row["question_id"] in q_map
    ]

    return AttemptResult(
        attempt_id=attempt.id,
        quiz_id=quiz.id,
        score=attempt.score,
        correct_count=attempt.correct_count,
        total_count=attempt.total_count,
        submitted_at=attempt.submitted_at,
        review=review,
    )


# ---------------------------------------------------------------------------
# GET /quiz/files/{file_id}/history
# ---------------------------------------------------------------------------

@router.get("/files/{file_id}/history", response_model=QuizHistoryResponse)
async def get_quiz_history(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _get_file_and_classroom(file_id, current_user, db)

    result = await db.execute(
        select(Quiz)
        .options(selectinload(Quiz.attempt))
        .where(Quiz.file_id == file_id, Quiz.user_id == current_user.id)
        .order_by(Quiz.created_at.desc())
    )
    quizzes = result.scalars().all()

    items = []
    open_quiz_id: int | None = None
    has_open = False

    for q in quizzes:
        attempt = q.attempt
        items.append(
            QuizHistoryItem(
                quiz_id=q.id,
                difficulty=q.difficulty.value,
                num_questions=q.num_questions,
                score=attempt.score if attempt else None,
                correct_count=attempt.correct_count if attempt else None,
                submitted_at=attempt.submitted_at if attempt else None,
                created_at=q.created_at,
                status=q.status.value,
            )
        )
        if q.status in _OPEN_STATUSES and not has_open:
            has_open = True
            open_quiz_id = q.id

    return QuizHistoryResponse(items=items, has_open_quiz=has_open, open_quiz_id=open_quiz_id)
