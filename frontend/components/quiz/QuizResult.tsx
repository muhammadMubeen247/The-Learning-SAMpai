"use client"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { AttemptResult } from "@/api/quiz"

interface Props {
  result: AttemptResult
  onGenerateNext: () => void
}

export function QuizResult({ result, onGenerateNext }: Props) {
  const pct = Math.round(result.score * 100)
  const scoreColor =
    pct >= 80 ? "text-green-400" : pct >= 50 ? "text-yellow-400" : "text-red-400"

  return (
    <div className="space-y-4 py-2">
      <div className="text-center space-y-1">
        <p className={cn("text-5xl font-bold", scoreColor)}>{pct}%</p>
        <p className="text-muted-foreground text-sm">
          {result.correct_count} / {result.total_count} correct
        </p>
      </div>

      <div className="space-y-3">
        {result.review.map((item) => (
          <div
            key={item.question_id}
            className={cn(
              "rounded-lg border p-3 text-sm space-y-1",
              item.correct ? "border-green-500/40 bg-green-500/5" : "border-red-500/40 bg-red-500/5"
            )}
          >
            <p className="font-medium">{item.prompt}</p>
            {item.type === "mcq" && item.options && (
              <div className="space-y-0.5 pl-1">
                {item.options.map((opt, idx) => {
                  const isCorrect = idx === item.correct_answer
                  const isUser = idx === item.user_answer
                  return (
                    <p
                      key={idx}
                      className={cn(
                        "text-xs",
                        isCorrect && "text-green-400 font-semibold",
                        isUser && !isCorrect && "text-red-400 line-through"
                      )}
                    >
                      {isCorrect ? "✓ " : isUser ? "✗ " : "  "}
                      {opt}
                    </p>
                  )
                })}
              </div>
            )}
            {item.type === "tf" && (
              <p className="text-xs text-muted-foreground">
                Your answer:{" "}
                <span className={item.correct ? "text-green-400" : "text-red-400"}>
                  {String(item.user_answer)}
                </span>
                {" · "}Correct: <span className="text-green-400">{String(item.correct_answer)}</span>
              </p>
            )}
            <p className="text-xs text-muted-foreground italic">{item.explanation}</p>
          </div>
        ))}
      </div>

      <Button onClick={onGenerateNext} className="w-full">
        Generate next quiz
      </Button>
    </div>
  )
}
