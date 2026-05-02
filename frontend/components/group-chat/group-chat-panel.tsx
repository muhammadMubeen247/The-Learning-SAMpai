"use client"

import { useState, useEffect, useCallback } from "react"
import { Wifi, WifiOff, Users, ChevronRight, ChevronLeft } from "lucide-react"
import { MessageList } from "./message-list"
import { MessageComposer } from "./message-composer"
import { ReplyContextBanner } from "./reply-context-banner"
import { TypingIndicator } from "./typing-indicator"
import { useGroupChatSocket, type GroupMessage } from "@/hooks/use-group-chat-socket"
import { toast } from "sonner"

type Member = {
  user_id: number
  role: string
  joined_at: string
  last_read_seq: number
  user: { id: number; username: string }
}

type Props = {
  groupChatId: number
  currentUserId: number
  members: Member[]
  filename: string
}

export function GroupChatPanel({ groupChatId, currentUserId, members, filename }: Props) {
  const {
    messages,
    typingUsers,
    agentTyping,
    onlineUserIds,
    connected,
    hasMore,
    loadingMore,
    send,
    sendTyping,
    sendReadReceipt,
    loadMore,
  } = useGroupChatSocket(groupChatId)

  const [replyingTo, setReplyingTo] = useState<GroupMessage | null>(null)
  const [sending, setSending] = useState(false)
  const [showMembers, setShowMembers] = useState(false)
  // Pre-filled composer content injected from outside (e.g. "@SAMpai " when replying to agent)
  const [composerSeed, setComposerSeed] = useState<string | undefined>(undefined)

  // Build member list for mention autocomplete
  const memberSummaries = members.map((m) => ({
    user_id: m.user_id,
    username: m.user.username,
  }))

  // Mark as read when messages arrive
  useEffect(() => {
    if (messages.length === 0) return
    const lastReal = [...messages]
      .reverse()
      .find((m) => typeof m.seq === "number" && m.seq > 0)
    if (lastReal) {
      sendReadReceipt(lastReal.seq as number)
    }
  }, [messages, sendReadReceipt])

  const handleReply = useCallback((msg: GroupMessage) => {
    setReplyingTo(msg)
    // When replying to an agent message, auto-trigger SAMpai
    if (msg.role === "agent") {
      setComposerSeed("@SAMpai ")
    }
  }, [])

  const handleSend = useCallback(
    async (content: string) => {
      setSending(true)
      try {
        const replyId = replyingTo?.id
        await send(content, typeof replyId === "number" ? replyId : undefined)
        setReplyingTo(null)
      } catch (err: unknown) {
        const status = (err as { response?: { status?: number } })?.response?.status
        if (status === 429) {
          toast.error("Message rate limit reached. Please slow down.")
        } else {
          toast.error("Failed to send message. Please try again.")
        }
      } finally {
        setSending(false)
      }
    },
    [send, replyingTo]
  )

  const onlineCount = onlineUserIds.length

  return (
    <div className="flex h-full bg-background">
      {/* Main chat column */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-card/50">
          <div className="min-w-0">
            <h2 className="font-semibold text-sm truncate">{filename}</h2>
            <div className="flex items-center gap-3 mt-0.5">
              <span className="flex items-center gap-1 text-xs text-muted-foreground">
                <Users className="w-3 h-3" />
                {members.length} member{members.length !== 1 ? "s" : ""}
              </span>
              {onlineCount > 0 && (
                <span className="text-xs text-green-400">{onlineCount} online</span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 text-xs">
              {connected ? (
                <Wifi className="w-4 h-4 text-green-400" />
              ) : (
                <WifiOff className="w-4 h-4 text-orange-400 animate-pulse" />
              )}
              <span className={connected ? "text-green-400" : "text-orange-400"}>
                {connected ? "Live" : "Reconnecting…"}
              </span>
            </div>
            <button
              onClick={() => setShowMembers((v) => !v)}
              className="ml-1 p-1.5 rounded-md hover:bg-muted/60 transition-colors text-muted-foreground hover:text-foreground"
              title={showMembers ? "Hide members" : "Show members"}
            >
              {showMembers ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {/* Message list */}
        <MessageList
          messages={messages}
          currentUserId={currentUserId}
          onReply={handleReply}
          hasMore={hasMore}
          loadingMore={loadingMore}
          onLoadMore={loadMore}
        />

        {/* Typing indicator */}
        <TypingIndicator typingUsers={typingUsers} agentTyping={agentTyping} />

        {/* Reply banner */}
        {replyingTo && (
          <ReplyContextBanner
            replyTo={replyingTo}
            onClear={() => { setReplyingTo(null); setComposerSeed(undefined) }}
          />
        )}

        {/* Composer */}
        <MessageComposer
          members={memberSummaries}
          currentUserId={currentUserId}
          disabled={sending}
          onSend={handleSend}
          onTyping={sendTyping}
          initialContent={composerSeed}
          onInitialContentConsumed={() => setComposerSeed(undefined)}
        />
      </div>

      {/* Members sidebar */}
      {showMembers && (
        <div className="w-56 border-l border-border bg-card/30 flex flex-col overflow-hidden shrink-0">
          <div className="px-3 py-2 border-b border-border">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Members</p>
          </div>
          <div className="flex-1 overflow-y-auto py-1">
            {members.map((m) => {
              const isOnline = onlineUserIds.includes(m.user_id)
              const isCurrentUser = m.user_id === currentUserId
              return (
                <div
                  key={m.user_id}
                  className="flex items-center gap-2 px-3 py-1.5"
                >
                  <div className="relative flex-shrink-0">
                    <div className="w-7 h-7 rounded-full bg-slate-600 flex items-center justify-center text-xs font-bold text-white">
                      {m.user.username[0]?.toUpperCase() ?? "?"}
                    </div>
                    <span
                      className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-card ${
                        isOnline ? "bg-green-400" : "bg-muted-foreground/40"
                      }`}
                    />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs text-foreground truncate">
                      {m.user.username}
                      {isCurrentUser && <span className="text-muted-foreground ml-1">(you)</span>}
                    </p>
                    <p className="text-[10px] text-muted-foreground capitalize">{m.role}</p>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
