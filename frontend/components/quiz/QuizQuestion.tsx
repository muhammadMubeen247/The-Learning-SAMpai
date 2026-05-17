"use client"

import type { QuestionPublic } from "@/api/quiz"

const LETTERS = ["A", "B", "C", "D", "E"]

interface Props {
  question: QuestionPublic
  value: string | undefined
  onChange: (val: string) => void
  disabled?: boolean
}

export function QuizQuestion({ question, value, onChange, disabled }: Props) {
  const makeOption = (val: string, label: string, letter?: string) => {
    const selected = value === val
    return (
      <button
        key={val}
        type="button"
        disabled={disabled}
        onClick={() => onChange(val)}
        className={`w-full text-left rounded-xl border text-sm transition-all flex items-center gap-3 px-4 py-3 ${
          disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer"
        } ${
          selected
            ? "border-chart-1/60 bg-chart-1/20 text-foreground shadow-sm"
            : "border-border/50 bg-card/60 text-foreground hover:border-chart-1/40 hover:bg-card/80"
        }`}
      >
        {letter && (
          <span
            className={`flex-none w-6 h-6 rounded-lg flex items-center justify-center text-xs font-bold shrink-0 transition-colors ${
              selected
                ? "bg-chart-1/30 text-chart-1"
                : "bg-border/30 text-muted-foreground"
            }`}
          >
            {letter}
          </span>
        )}
        <span className="leading-relaxed">{label}</span>
      </button>
    )
  }

  if (question.type === "mcq" && question.options) {
    return (
      <div className="space-y-3">
        <p className="font-semibold text-sm leading-relaxed text-foreground">{question.prompt}</p>
        <div className="space-y-2">
          {question.options.map((opt, idx) => makeOption(String(idx), opt, LETTERS[idx]))}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <p className="font-semibold text-sm leading-relaxed text-foreground">{question.prompt}</p>
      <div className="flex gap-2">
        {makeOption("true", "True")}
        {makeOption("false", "False")}
      </div>
    </div>
  )
}
