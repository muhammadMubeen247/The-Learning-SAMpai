"use client"

import type { TypingState } from "@/hooks/use-group-chat-socket"

type Props = {
  typingUsers: TypingState[]
  agentTyping: boolean
}

export function TypingIndicator({ typingUsers, agentTyping }: Props) {
  const labels: string[] = []
  if (agentTyping) labels.push("SAMpai is thinking")
  for (const t of typingUsers) {
    labels.push(`${t.username} is typing`)
  }

  if (labels.length === 0) return null

  return (
    <div className="px-4 py-1 flex items-center gap-2 text-xs text-muted-foreground">
      <span className="flex gap-0.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce"
            style={{ animationDelay: `${i * 150}ms` }}
          />
        ))}
      </span>
      <span>{labels.join(" · ")}</span>
    </div>
  )
}
