"use client"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { QuizHistoryItem } from "@/api/quiz"

interface Props {
  items: QuizHistoryItem[]
}

const DIFFICULTY_COLOR: Record<string, string> = {
  easy: "border-green-500/50 text-green-400",
  medium: "border-yellow-500/50 text-yellow-400",
  hard: "border-red-500/50 text-red-400",
}

const STATUS_LABEL: Record<string, string> = {
  pending: "Pending",
  generating: "Generating…",
  ready: "Ready",
  failed: "Failed",
  submitted: "Submitted",
}

export function QuizHistory({ items }: Props) {
  if (!items.length) {
    return (
      <p className="text-muted-foreground text-sm text-center py-4">No quiz history yet.</p>
    )
  }

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
        Past Quizzes
      </p>
      <div className="space-y-1.5">
        {items.map((item) => (
          <div
            key={item.quiz_id}
            className="flex items-center justify-between rounded-lg border border-border bg-card/40 px-3 py-2 text-sm"
          >
            <div className="flex items-center gap-2">
              <Badge
                variant="outline"
                className={cn("capitalize text-xs", DIFFICULTY_COLOR[item.difficulty])}
              >
                {item.difficulty}
              </Badge>
              <span className="text-muted-foreground text-xs">{item.num_questions}q</span>
            </div>
            <div className="text-right">
              {item.score != null ? (
                <span
                  className={cn(
                    "font-semibold text-xs",
                    item.score >= 0.8
                      ? "text-green-400"
                      : item.score >= 0.5
                        ? "text-yellow-400"
                        : "text-red-400"
                  )}
                >
                  {Math.round(item.score * 100)}%
                </span>
              ) : (
                <span className="text-muted-foreground text-xs">{STATUS_LABEL[item.status]}</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
