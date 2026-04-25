"use client"

import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import type { QuestionPublic } from "@/api/quiz"

interface Props {
  question: QuestionPublic
  value: string | undefined
  onChange: (val: string) => void
  disabled?: boolean
}

export function QuizQuestion({ question, value, onChange, disabled }: Props) {
  if (question.type === "mcq" && question.options) {
    return (
      <div className="space-y-2">
        <p className="font-medium text-sm leading-relaxed">{question.prompt}</p>
        <RadioGroup value={value ?? ""} onValueChange={onChange} disabled={disabled}>
          {question.options.map((opt, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <RadioGroupItem value={String(idx)} id={`q${question.id}-opt${idx}`} />
              <Label htmlFor={`q${question.id}-opt${idx}`} className="cursor-pointer text-sm">
                {opt}
              </Label>
            </div>
          ))}
        </RadioGroup>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <p className="font-medium text-sm leading-relaxed">{question.prompt}</p>
      <RadioGroup value={value ?? ""} onValueChange={onChange} disabled={disabled}>
        <div className="flex items-center gap-2">
          <RadioGroupItem value="true" id={`q${question.id}-true`} />
          <Label htmlFor={`q${question.id}-true`} className="cursor-pointer text-sm">True</Label>
        </div>
        <div className="flex items-center gap-2">
          <RadioGroupItem value="false" id={`q${question.id}-false`} />
          <Label htmlFor={`q${question.id}-false`} className="cursor-pointer text-sm">False</Label>
        </div>
      </RadioGroup>
    </div>
  )
}
