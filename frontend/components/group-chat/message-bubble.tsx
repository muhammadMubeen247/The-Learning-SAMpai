"use client"

import { useRef, useEffect } from "react"
import { CornerUpLeft } from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import type { GroupMessage } from "@/hooks/use-group-chat-socket"

type Props = {
  message: GroupMessage
  currentUserId: number | null
  highlight?: boolean
  onReplyClick?: (msg: GroupMessage) => void
  replyTarget?: GroupMessage | null
  onScrollTo?: (messageId: number) => void
}

function renderMentions(content: string): React.ReactNode[] {
  const parts = content.split(/(@\w+)/g)
  return parts.map((part, i) => {
    if (/^@\w+$/.test(part)) {
      const isAgent = part.toLowerCase() === "@sampai"
      return (
        <span
          key={i}
          className={`inline-block px-1 rounded text-xs font-semibold ${
            isAgent
              ? "bg-violet-500/20 text-violet-400"
              : "bg-blue-500/20 text-blue-400"
          }`}
        >
          {part}
        </span>
      )
    }
    return <span key={i}>{part}</span>
  })
}

export function MessageBubble({
  message,
  currentUserId,
  highlight,
  onReplyClick,
  replyTarget,
  onScrollTo,
}: Props) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (highlight && ref.current) {
      ref.current.scrollIntoView({ behavior: "smooth", block: "center" })
      ref.current.classList.add("ring-2", "ring-violet-400")
      const t = setTimeout(() => {
        ref.current?.classList.remove("ring-2", "ring-violet-400")
      }, 1500)
      return () => clearTimeout(t)
    }
  }, [highlight])

  const isMe = message.user_id === currentUserId
  const isAgent = message.role === "agent"
  const isSystem = message.role === "system"
  const isTemp = String(message.id).startsWith("temp:")

  if (isSystem) {
    return (
      <div className="flex justify-center my-2">
        <span className="text-xs text-muted-foreground bg-muted/50 px-3 py-1 rounded-full">
          {message.content}
        </span>
      </div>
    )
  }

  return (
    <div
      ref={ref}
      className={`flex gap-2 px-4 py-1 transition-all duration-300 group ${
        isMe ? "flex-row-reverse" : "flex-row"
      } ${isTemp ? "opacity-60" : ""}`}
    >
      {/* Avatar */}
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white ${
          isAgent ? "bg-violet-600" : isMe ? "bg-blue-600" : "bg-slate-600"
        }`}
      >
        {isAgent ? "AI" : (message.author?.username?.[0]?.toUpperCase() ?? "?")}
      </div>

      <div className={`max-w-[70%] flex flex-col gap-1 ${isMe ? "items-end" : "items-start"}`}>
        {/* Author name */}
        <span className="text-xs text-muted-foreground px-1">
          {isAgent ? "SAMpai" : (message.author?.username ?? (isMe ? "You" : "Unknown"))}
        </span>

        {/* Reply context */}
        {replyTarget && (
          <button
            onClick={() => replyTarget.id && typeof replyTarget.id === "number" && onScrollTo?.(replyTarget.id)}
            className="text-xs text-muted-foreground bg-muted/40 border-l-2 border-violet-400 px-2 py-1 rounded text-left truncate max-w-full hover:bg-muted/60 transition-colors"
          >
            <span className="font-medium">{replyTarget.author?.username ?? "SAMpai"}: </span>
            {replyTarget.content.slice(0, 80)}{replyTarget.content.length > 80 ? "…" : ""}
          </button>
        )}

        {/* Bubble + reply arrow */}
        <div className={`flex items-end gap-1.5 ${isMe ? "flex-row" : "flex-row-reverse"}`}>
          {/* Reply arrow — shown on hover, on the open/inward side of the bubble */}
          <button
            onClick={() => onReplyClick?.(message)}
            className="opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0 w-6 h-6 flex items-center justify-center rounded-full hover:bg-muted/60 text-muted-foreground hover:text-foreground"
            title="Reply"
            aria-label="Reply to this message"
          >
            <CornerUpLeft className="w-3.5 h-3.5" />
          </button>

          <div
            className={`rounded-2xl px-3 py-2 text-sm leading-relaxed ${
              message.is_discarded
                ? "opacity-50 line-through bg-muted/30 text-muted-foreground"
                : isAgent
                ? "bg-violet-900/40 text-foreground border border-violet-500/30"
                : isMe
                ? "bg-blue-600 text-white"
                : "bg-muted text-foreground"
            }`}
          >
            {isAgent ? (
              <div className="prose prose-sm dark:prose-invert max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {message.content}
                </ReactMarkdown>
              </div>
            ) : (
              <p className="whitespace-pre-wrap break-words">
                {renderMentions(message.content)}
              </p>
            )}

            {message.is_discarded && (
              <span className="block mt-1 text-[10px] not-italic font-normal no-underline text-orange-400/80">
                removed by SAMpai: {message.discard_reason ?? "off-topic"}
              </span>
            )}
          </div>
        </div>

        {/* Timestamp */}
        <span className="text-[10px] text-muted-foreground px-1">
          {new Date(message.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </span>
      </div>
    </div>
  )
}
