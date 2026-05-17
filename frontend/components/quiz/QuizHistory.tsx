"use client"

import type { QuizHistoryItem } from "@/api/quiz"

interface Props {
  items: QuizHistoryItem[]
}

const DIFFICULTY_COLOR: Record<string, string> = {
  easy:   "border-emerald-500/40 bg-emerald-500/10 text-emerald-400",
  medium: "border-amber-500/40 bg-amber-500/10 text-amber-400",
  hard:   "border-red-500/40 bg-red-500/10 text-red-400",
}

const STATUS_LABEL: Record<string, string> = {
  pending:    "Pending",
  generating: "Generating…",
  ready:      "Ready",
  failed:     "Failed",
  submitted:  "Submitted",
}

export function QuizHistory({ items }: Props) {
  if (!items.length) {
    return (
      <p className="text-muted-foreground/50 text-xs text-center py-4">No quiz history yet.</p>
    )
  }

  return (
    <div className="space-y-2">
      <p className="text-[10px] font-semibold text-muted-foreground/50 uppercase tracking-wider">
        Past Quizzes
      </p>
      <div className="space-y-1.5">
        {items.map((item) => (
          <div
            key={item.quiz_id}
            className="flex items-center justify-between rounded-xl border border-border/40 bg-card/60 backdrop-blur-sm px-3 py-2.5"
          >
            <div className="flex items-center gap-2">
              <span
                className={`capitalize text-[11px] font-medium px-2 py-0.5 rounded-full border ${
                  DIFFICULTY_COLOR[item.difficulty] ?? "border-border/40 bg-card/20 text-muted-foreground"
                }`}
              >
                {item.difficulty}
              </span>
              <span className="text-muted-foreground/60 text-xs">{item.num_questions}q</span>
            </div>
            <div className="text-right">
              {item.score != null ? (
                <span
                  className={`font-semibold text-sm tabular-nums ${
                    item.score >= 0.8
                      ? "text-emerald-400"
                      : item.score >= 0.5
                      ? "text-amber-400"
                      : "text-red-400"
                  }`}
                >
                  {Math.round(item.score * 100)}%
                </span>
              ) : (
                <span className="text-muted-foreground/50 text-xs">{STATUS_LABEL[item.status]}</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
