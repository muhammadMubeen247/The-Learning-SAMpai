"use client"

import type { AttemptResult } from "@/api/quiz"

const LETTERS = ["A", "B", "C", "D", "E"]

interface Props {
  result: AttemptResult
  onGenerateNext: () => void
  onBack: () => void
}

export function QuizResult({ result, onGenerateNext, onBack }: Props) {
  const pct = Math.round(result.score * 100)
  const scoreColor =
    pct >= 80 ? "text-emerald-400" : pct >= 50 ? "text-amber-400" : "text-red-400"

  return (
    <div className="space-y-5 py-2">
      {/* Score */}
      <div className="text-center py-5 space-y-1">
        <p className={`text-6xl font-bold tabular-nums ${scoreColor}`}>{pct}%</p>
        <p className="text-muted-foreground text-sm">
          {result.correct_count} / {result.total_count} correct
        </p>
      </div>

      {/* Review */}
      <div className="space-y-2.5">
        {result.review.map((item) => (
          <div
            key={item.question_id}
            className={`rounded-2xl border p-4 text-sm space-y-3 backdrop-blur-sm ${
              item.correct
                ? "border-emerald-500/40 bg-emerald-500/15"
                : "border-red-500/40 bg-red-500/15"
            }`}
          >
            <p className="font-semibold text-foreground leading-snug">{item.prompt}</p>

            {item.type === "mcq" && item.options && (
              <div className="space-y-1.5">
                {item.options.map((opt, idx) => {
                  const isCorrect = idx === item.correct_answer
                  const isUser = idx === item.user_answer
                  const letter = LETTERS[idx]
                  return (
                    <div
                      key={idx}
                      className={`flex items-start gap-2 text-xs rounded-lg px-2.5 py-1.5 ${
                        isCorrect
                          ? "bg-emerald-500/15 border border-emerald-500/30"
                          : isUser && !isCorrect
                          ? "bg-red-500/15 border border-red-500/30"
                          : "border border-transparent"
                      }`}
                    >
                      <span
                        className={`flex-none w-5 h-5 rounded-md flex items-center justify-center text-[10px] font-bold shrink-0 ${
                          isCorrect
                            ? "bg-emerald-500/30 text-emerald-400"
                            : isUser && !isCorrect
                            ? "bg-red-500/30 text-red-400"
                            : "bg-border/30 text-muted-foreground/60"
                        }`}
                      >
                        {letter}
                      </span>
                      <span
                        className={`leading-relaxed ${
                          isCorrect
                            ? "text-emerald-400 font-medium"
                            : isUser && !isCorrect
                            ? "text-red-400 line-through"
                            : "text-muted-foreground/60"
                        }`}
                      >
                        {opt}
                      </span>
                      {isCorrect && (
                        <span className="ml-auto text-emerald-400 shrink-0">✓</span>
                      )}
                      {isUser && !isCorrect && (
                        <span className="ml-auto text-red-400 shrink-0">✗</span>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

            {item.type === "tf" && (
              <div className="flex gap-3 text-xs">
                <span className="text-muted-foreground/70">Your answer:</span>
                <span className={item.correct ? "text-emerald-400 font-medium" : "text-red-400 font-medium line-through"}>
                  {item.user_answer === true ? "True" : "False"}
                </span>
                {!item.correct && (
                  <>
                    <span className="text-muted-foreground/40">·</span>
                    <span className="text-muted-foreground/70">Correct:</span>
                    <span className="text-emerald-400 font-medium">
                      {item.correct_answer === true ? "True" : "False"}
                    </span>
                  </>
                )}
              </div>
            )}

            {item.explanation && (
              <p className="text-xs text-muted-foreground/70 italic leading-relaxed border-t border-border/30 pt-2">
                {item.explanation}
              </p>
            )}
          </div>
        ))}
      </div>

      {/* Actions */}
      <div className="flex flex-col gap-2 pb-2">
        <button
          type="button"
          onClick={onGenerateNext}
          className="w-full py-2.5 rounded-xl bg-chart-1/80 hover:bg-chart-1 text-foreground text-sm font-medium transition-colors cursor-pointer"
        >
          Generate next quiz
        </button>
        <button
          type="button"
          onClick={onBack}
          className="w-full py-2 rounded-xl text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
        >
          ← Back
        </button>
      </div>
    </div>
  )
}
