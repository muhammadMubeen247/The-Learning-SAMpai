"use client"

import { X } from "lucide-react"
import type { GroupMessage } from "@/hooks/use-group-chat-socket"

type Props = {
  replyTo: GroupMessage
  onClear: () => void
}

export function ReplyContextBanner({ replyTo, onClear }: Props) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 bg-muted/50 border-t border-border text-xs">
      <div className="flex-1 min-w-0 border-l-2 border-violet-400 pl-2">
        <span className="font-medium text-foreground">
          {replyTo.role === "agent" ? "SAMpai" : (replyTo.author?.username ?? "Unknown")}
        </span>
        <p className="text-muted-foreground truncate">{replyTo.content.slice(0, 100)}</p>
      </div>
      <button
        onClick={onClear}
        className="flex-shrink-0 text-muted-foreground hover:text-foreground transition-colors"
        aria-label="Cancel reply"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  )
}
