"use client"

import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { ScrollArea } from "@/components/ui/scroll-area"
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

  const pollStartRef = useRef<number>(0)

  // Load history and resume any open quiz on mount
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

  // Polling while generating
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
      const msg =
        err?.response?.data?.detail ?? "Failed to start quiz generation."
      setErrorMsg(msg)
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
        let answer: number | boolean
        if (q.type === "tf") {
          answer = raw === "true"
        } else {
          answer = raw != null ? Number(raw) : -1
        }
        return { question_id: q.id, answer }
      })
      const res = await submitQuiz(quizId, payload)
      setResult(res)
      setState("submitted")
      // Refresh history
      getQuizHistory(fileId)
        .then((h) => setHistory(h.items))
        .catch(() => {})
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
    getQuizHistory(fileId)
      .then((h) => setHistory(h.items))
      .catch(() => {})
  }

  if (!canQuiz) {
    return (
      <div className="flex-1 flex items-center justify-center p-6">
        <p className="text-muted-foreground text-sm text-center">
          Quiz will be available once this file finishes processing.
        </p>
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 gap-3 p-4">
      {/* Error banner */}
      {errorMsg && (
        <Alert variant="destructive">
          <AlertDescription className="text-xs">{errorMsg}</AlertDescription>
        </Alert>
      )}

      {/* ── IDLE: setup form ── */}
      {state === "idle" && (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-3">
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground font-medium">Questions</p>
              <Select
                value={numQuestions}
                onValueChange={(v) => setNumQuestions(v as "5" | "10" | "15")}
              >
                <SelectTrigger className="w-24 h-8 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="5">5</SelectItem>
                  <SelectItem value="10">10</SelectItem>
                  <SelectItem value="15">15</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground font-medium">Difficulty</p>
              <Select
                value={difficulty}
                onValueChange={(v) => setDifficulty(v as Difficulty | "auto")}
              >
                <SelectTrigger className="w-28 h-8 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">Auto</SelectItem>
                  <SelectItem value="easy">Easy</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="hard">Hard</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <Button onClick={handleGenerate} className="w-full">
            Generate quiz
          </Button>
          <QuizHistory items={history} />
        </div>
      )}

      {/* ── GENERATING: spinner ── */}
      {state === "generating" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-3">
          <div className="h-8 w-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
          <p className="text-sm text-muted-foreground">Generating your quiz…</p>
        </div>
      )}

      {/* ── IN PROGRESS: questions ── */}
      {state === "in_progress" && (
        <div className="flex-1 flex flex-col min-h-0 gap-3">
          <ScrollArea className="flex-1 min-h-0">
            <div className="space-y-5 pr-2">
              {questions.map((q, idx) => (
                <div
                  key={q.id}
                  className="rounded-xl border border-border bg-card/40 p-4 space-y-2"
                >
                  <p className="text-xs text-muted-foreground font-medium">
                    Question {idx + 1} of {questions.length}
                  </p>
                  <QuizQuestion
                    question={q}
                    value={answers[q.id]}
                    onChange={(val) =>
                      setAnswers((prev) => ({ ...prev, [q.id]: val }))
                    }
                    disabled={submitting}
                  />
                </div>
              ))}
            </div>
          </ScrollArea>
          <Button onClick={handleSubmit} disabled={submitting} className="shrink-0">
            {submitting ? "Submitting…" : "Submit quiz"}
          </Button>
        </div>
      )}

      {/* ── SUBMITTED: results ── */}
      {state === "submitted" && result && (
        <ScrollArea className="flex-1 min-h-0">
          <div className="pr-2">
            <QuizResult result={result} onGenerateNext={handleGenerateNext} />
          </div>
        </ScrollArea>
      )}

      {/* ── ERROR: retry ── */}
      {state === "error" && (
        <div className="flex flex-col items-center gap-3 pt-4">
          <Button variant="outline" onClick={handleGenerateNext}>
            Back to setup
          </Button>
        </div>
      )}
    </div>
  )
}
