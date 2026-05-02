"use client"

import { useEffect, useRef, useState, useCallback } from "react"
import { useVirtualizer } from "@tanstack/react-virtual"
import { Loader2 } from "lucide-react"
import { MessageBubble } from "./message-bubble"
import type { GroupMessage } from "@/hooks/use-group-chat-socket"

type Props = {
  messages: GroupMessage[]
  currentUserId: number | null
  onReply: (msg: GroupMessage) => void
  hasMore: boolean
  loadingMore: boolean
  onLoadMore: () => void
}

export function MessageList({ messages, currentUserId, onReply, hasMore, loadingMore, onLoadMore }: Props) {
  const parentRef = useRef<HTMLDivElement>(null)
  const [highlightId, setHighlightId] = useState<number | null>(null)

  // Build a lookup for reply targets
  const msgById = useRef<Map<number | string, GroupMessage>>(new Map())
  useEffect(() => {
    msgById.current.clear()
    for (const m of messages) msgById.current.set(m.id, m)
  }, [messages])

  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 80,
    overscan: 10,
  })

  // Auto-scroll to bottom unless user scrolled up >100px
  const isAtBottomRef = useRef(true)
  const prevCountRef = useRef(messages.length)
  // Remember scroll height before prepending so we can restore position
  const prevScrollHeightRef = useRef(0)

  useEffect(() => {
    const el = parentRef.current
    if (!el) return

    const handleScroll = () => {
      const fromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
      isAtBottomRef.current = fromBottom < 100

      // Trigger load-more when user scrolls near the top
      if (el.scrollTop < 80 && !loadingMore) {
        onLoadMore()
      }
    }
    el.addEventListener("scroll", handleScroll, { passive: true })
    return () => el.removeEventListener("scroll", handleScroll)
  }, [loadingMore, onLoadMore])

  useEffect(() => {
    if (messages.length > prevCountRef.current && isAtBottomRef.current) {
      virtualizer.scrollToIndex(messages.length - 1, { align: "end", behavior: "smooth" })
    }
    prevCountRef.current = messages.length
  }, [messages.length, virtualizer])

  const scrollToMessage = useCallback((id: number) => {
    const idx = messages.findIndex((m) => m.id === id)
    if (idx === -1) return
    virtualizer.scrollToIndex(idx, { align: "center", behavior: "smooth" })
    setHighlightId(id)
    setTimeout(() => setHighlightId(null), 1600)
  }, [messages, virtualizer])

  const items = virtualizer.getVirtualItems()

  return (
    <div
      ref={parentRef}
      className="flex-1 overflow-y-auto overflow-x-hidden"
    >
      {/* Load-more indicator at top */}
      {hasMore && (
        <div className="flex justify-center py-2">
          {loadingMore ? (
            <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
          ) : (
            <button
              onClick={onLoadMore}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors px-3 py-1 rounded-full border border-border hover:bg-muted/50"
            >
              Load older messages
            </button>
          )}
        </div>
      )}

      <div
        style={{
          height: virtualizer.getTotalSize(),
          width: "100%",
          position: "relative",
        }}
      >
        {items.map((item) => {
          const msg = messages[item.index]
          const replyTarget = msg.reply_to_id
            ? (msgById.current.get(msg.reply_to_id) ?? null)
            : null

          return (
            <div
              key={item.key}
              data-index={item.index}
              ref={virtualizer.measureElement}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                transform: `translateY(${item.start}px)`,
              }}
            >
              <MessageBubble
                message={msg}
                currentUserId={currentUserId}
                highlight={highlightId === msg.id}
                onReplyClick={onReply}
                replyTarget={replyTarget}
                onScrollTo={scrollToMessage}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}
