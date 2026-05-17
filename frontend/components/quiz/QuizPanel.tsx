"use client"

import { useEffect, useRef, useState } from "react"
import { motion } from "framer-motion"
import { BookOpen } from "lucide-react"
import { QuizQuestion } from "./QuizQuestion"
import { QuizResult } from "./QuizResult"
import { QuizHistory } from "./QuizHistory"
import {
  generateQuiz,
  getQuiz,
  submitQuiz,
  getQuizHistory,
  type Difficulty,
  type QuestionPublic,
  type AttemptResult,
  type QuizHistoryItem,
} from "@/api/quiz"

type PanelState = "idle" | "generating" | "in_progress" | "submitted" | "error"

interface Props {
  fileId: number
  canQuiz: boolean
}

const POLL_INTERVAL_MS = 2000
const POLL_TIMEOUT_MS = 60_000

export function QuizPanel({ fileId, canQuiz }: Props) {
  const [state, setState] = useState<PanelState>("idle")
  const [quizId, setQuizId] = useState<number | null>(null)
  const [questions, setQuestions] = useState<QuestionPublic[]>([])
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [result, setResult] = useState<AttemptResult | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [history, setHistory] = useState<QuizHistoryItem[]>([])
  const [numQuestions, setNumQuestions] = useState<"5" | "10" | "15">("10")
  const [difficulty, setDifficulty] = useState<Difficulty | "auto">("auto")
  const [submitting, setSubmitting] = useState(false)
  const [showHistory, setShowHistory] = useState(false)

  const pollStartRef = useRef<number>(0)

  useEffect(() => {
    if (!canQuiz) return
    getQuizHistory(fileId)
      .then((hist) => {
        setHistory(hist.items)
        if (hist.has_open_quiz && hist.open_quiz_id != null) {
          resumeQuiz(hist.open_quiz_id)
        }
      })
      .catch(() => {})
  }, [fileId, canQuiz]) // eslint-disable-line react-hooks/exhaustive-deps

  async function resumeQuiz(id: number) {
    setQuizId(id)
    try {
      const detail = await getQuiz(id)
      if (detail.status === "ready" && detail.questions) {
        setQuestions(detail.questions)
        setAnswers({})
        setState("in_progress")
      } else if (detail.status === "submitted" && detail.attempt) {
        setResult(detail.attempt)
        setState("submitted")
      } else if (detail.status === "pending" || detail.status === "generating") {
        pollStartRef.current = Date.now()
        setState("generating")
      } else if (detail.status === "failed") {
        setErrorMsg(detail.error_msg ?? "Generation failed.")
        setState("error")
      }
    } catch {
      setState("idle")
    }
  }

  useEffect(() => {
    if (state !== "generating" || quizId == null) return
    const interval = setInterval(async () => {
      if (Date.now() - pollStartRef.current > POLL_TIMEOUT_MS) {
        clearInterval(interval)
        setErrorMsg("Quiz generation timed out. Please try again.")
        setState("error")
        return
      }
      try {
        const detail = await getQuiz(quizId)
        if (detail.status === "ready" && detail.questions) {
          clearInterval(interval)
          setQuestions(detail.questions)
          setAnswers({})
          setState("in_progress")
        } else if (detail.status === "failed") {
          clearInterval(interval)
          setErrorMsg(detail.error_msg ?? "Generation failed.")
          setState("error")
        }
      } catch {
        // transient — let loop retry
      }
    }, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [state, quizId])

  async function handleGenerate() {
    setErrorMsg(null)
    try {
      const res = await generateQuiz(fileId, {
        num_questions: Number(numQuestions) as 5 | 10 | 15,
        difficulty: difficulty === "auto" ? undefined : difficulty,
      })
      setQuizId(res.quiz_id)
      pollStartRef.current = Date.now()
      setState("generating")
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail ?? "Failed to start quiz generation.")
    }
  }

  async function handleSubmit() {
    if (quizId == null) return
    const unanswered = questions.filter((q) => answers[q.id] == null)
    if (unanswered.length > 0) {
      const ok = window.confirm(
        `${unanswered.length} question(s) unanswered — they will count as wrong. Submit anyway?`
      )
      if (!ok) return
    }
    setSubmitting(true)
    try {
      const payload = questions.map((q) => {
        const raw = answers[q.id]
        let answer: number | boolean | null
        if (raw == null) {
          answer = null
        } else if (q.type === "tf") {
          answer = raw === "true"
        } else {
          answer = Number(raw)
        }
        return { question_id: q.id, answer }
      })
      const res = await submitQuiz(quizId, payload)
      setResult(res)
      setState("submitted")
      getQuizHistory(fileId).then((h) => setHistory(h.items)).catch(() => {})
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail ?? "Failed to submit quiz.")
    } finally {
      setSubmitting(false)
    }
  }

  function handleGenerateNext() {
    setQuizId(null)
    setQuestions([])
    setAnswers({})
    setResult(null)
    setErrorMsg(null)
    setState("idle")
    getQuizHistory(fileId).then((h) => setHistory(h.items)).catch(() => {})
  }

  function handleBack() {
    setQuizId(null)
    setQuestions([])
    setAnswers({})
    setResult(null)
    setErrorMsg(null)
    setState("idle")
    getQuizHistory(fileId).then((h) => setHistory(h.items)).catch(() => {})
  }

  if (!canQuiz) {
    return (
      <div className="flex-1 flex items-center justify-center p-6">
        <p className="text-muted-foreground text-sm text-center">
          Quiz will be available once full analysis finishes.
        </p>
      </div>
    )
  }

  const answeredCount = Object.keys(answers).length

  return (
    <div className="flex-1 flex flex-col min-h-0">

      {/* ── IDLE ── */}
      {state === "idle" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-8 px-8 py-6">

          {/* Icon + heading */}
          <div className="text-center space-y-2">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl border border-border/40 bg-card/40 backdrop-blur-sm mb-1">
              <BookOpen className="w-7 h-7 text-chart-1" />
            </div>
            <p className="text-base font-semibold text-foreground">Quiz</p>
            <p className="text-xs text-muted-foreground/70 max-w-xs">
              {history.length > 0
                ? "Test your knowledge from this document."
                : "AI-generated questions grounded in this document."}
            </p>
          </div>

          {/* Error */}
          {errorMsg && (
            <p className="text-xs text-destructive text-center max-w-xs">{errorMsg}</p>
          )}

          {/* Settings + generate */}
          <div className="w-full max-w-xs space-y-4">
            {/* Number of questions */}
            <div className="space-y-2">
              <p className="text-[11px] text-muted-foreground/60 font-medium text-center">Questions</p>
              <div className="flex gap-2">
                {(["5", "10", "15"] as const).map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => setNumQuestions(n)}
                    className={`flex-1 py-2 rounded-xl border text-sm font-medium transition-all cursor-pointer ${
                      numQuestions === n
                        ? "border-chart-1/60 bg-chart-1/20 text-foreground"
                        : "border-border/40 bg-card/20 text-muted-foreground hover:border-border/60 hover:text-foreground"
                    }`}
                  >
                    {n}
                  </button>
                ))}
              </div>
            </div>

            {/* Difficulty */}
            <div className="space-y-2">
              <p className="text-[11px] text-muted-foreground/60 font-medium text-center">Difficulty</p>
              <div className="flex gap-2">
                {(["auto", "easy", "medium", "hard"] as const).map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setDifficulty(d)}
                    className={`flex-1 py-2 rounded-xl border text-xs font-medium capitalize transition-all cursor-pointer ${
                      difficulty === d
                        ? "border-chart-1/60 bg-chart-1/20 text-foreground"
                        : "border-border/40 bg-card/20 text-muted-foreground hover:border-border/60 hover:text-foreground"
                    }`}
                  >
                    {d}
                  </button>
                ))}
              </div>
            </div>

            <button
              type="button"
              onClick={handleGenerate}
              className="w-full py-2.5 rounded-xl bg-chart-1/80 hover:bg-chart-1 text-foreground text-sm font-medium transition-colors cursor-pointer"
            >
              Generate quiz
            </button>
          </div>

          {/* Collapsible history */}
          {history.length > 0 && (
            <div className="w-full max-w-xs">
              <button
                type="button"
                onClick={() => setShowHistory((v) => !v)}
                className="w-full text-[11px] text-muted-foreground/50 hover:text-muted-foreground transition-colors cursor-pointer text-center"
              >
                {showHistory ? "Hide history" : `${history.length} past quiz${history.length !== 1 ? "zes" : ""}`}
              </button>
              {showHistory && (
                <div className="mt-2 max-h-48 overflow-y-auto">
                  <QuizHistory items={history} />
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── GENERATING ── */}
      {state === "generating" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-4">
          <div className="flex gap-1.5 items-center">
            {[0, 1, 2].map((i) => (
              <motion.span
                key={i}
                className="block w-2 h-2 rounded-full bg-chart-1/70"
                animate={{ y: [0, -6, 0] }}
                transition={{ duration: 0.9, delay: i * 0.18, repeat: Infinity, ease: "easeInOut" }}
              />
            ))}
          </div>
          <p className="text-sm text-muted-foreground">Generating your quiz…</p>
          <p className="text-xs text-muted-foreground/50">This may take up to a minute.</p>
        </div>
      )}

      {/* ── IN PROGRESS ── */}
      {state === "in_progress" && (
        <div className="flex-1 flex flex-col min-h-0 gap-3 p-5">
          {/* Error */}
          {errorMsg && (
            <div className="shrink-0 px-4 py-2.5 rounded-xl border border-destructive/40 bg-destructive/10 text-xs text-destructive">
              {errorMsg}
            </div>
          )}

          {/* Progress */}
          <div className="shrink-0 space-y-1.5">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{answeredCount} answered</span>
              <span>{questions.length} total</span>
            </div>
            <div className="h-1.5 rounded-full bg-border/30 overflow-hidden">
              <div
                className="h-full bg-chart-1/60 rounded-full transition-all duration-300"
                style={{ width: `${questions.length ? (answeredCount / questions.length) * 100 : 0}%` }}
              />
            </div>
          </div>

          {/* Questions */}
          <div className="flex-1 min-h-0 overflow-y-auto space-y-3 pr-0.5">
            {questions.map((q, idx) => (
              <div
                key={q.id}
                className="rounded-2xl border border-border/50 bg-card/80 backdrop-blur-sm p-4 shadow-sm"
              >
                <p className="text-[11px] text-muted-foreground/60 font-medium mb-2.5 uppercase tracking-wide">Q{idx + 1}</p>
                <QuizQuestion
                  question={q}
                  value={answers[q.id]}
                  onChange={(val) => setAnswers((prev) => ({ ...prev, [q.id]: val }))}
                  disabled={submitting}
                />
              </div>
            ))}
          </div>

          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting}
            className="shrink-0 w-full py-2.5 rounded-xl bg-chart-1/80 hover:bg-chart-1 text-foreground text-sm font-medium transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? "Submitting…" : `Submit quiz (${answeredCount}/${questions.length})`}
          </button>
        </div>
      )}

      {/* ── SUBMITTED ── */}
      {state === "submitted" && result && (
        <div className="flex-1 min-h-0 overflow-y-auto px-5 pr-4">
          <QuizResult result={result} onGenerateNext={handleGenerateNext} onBack={handleBack} />
        </div>
      )}

      {/* ── ERROR ── */}
      {state === "error" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 p-5">
          {errorMsg && (
            <p className="text-xs text-destructive text-center max-w-xs">{errorMsg}</p>
          )}
          <button
            type="button"
            onClick={handleBack}
            className="px-6 py-2.5 rounded-xl border border-border/40 bg-card/30 text-sm text-foreground hover:bg-card/50 cursor-pointer transition-colors"
          >
            Back to setup
          </button>
        </div>
      )}

    </div>
  )
}
