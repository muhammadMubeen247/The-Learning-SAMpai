"use client"

import { useState, useRef, useCallback, useEffect, KeyboardEvent } from "react"
import { Send } from "lucide-react"
import { MentionAutocomplete, forwardKeyToMentionAutocomplete } from "./mention-autocomplete"

type Member = {
  user_id: number
  username: string
}

type Props = {
  members: Member[]
  currentUserId?: number
  disabled?: boolean
  onSend: (content: string) => void
  onTyping: () => void
  /** Pre-filled content injected from outside (e.g. "@SAMpai " when replying to agent) */
  initialContent?: string
  onInitialContentConsumed?: () => void
}

function detectMentionAtCaret(value: string, caret: number): string | null {
  const before = value.slice(0, caret)
  const match = before.match(/@(\w*)$/)
  return match ? match[1] : null
}

export function MessageComposer({
  members,
  currentUserId,
  disabled,
  onSend,
  onTyping,
  initialContent,
  onInitialContentConsumed,
}: Props) {
  const [content, setContent] = useState("")
  const [mentionQuery, setMentionQuery] = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const autocompleteRef = useRef<HTMLDivElement>(null)

  // Inject pre-filled content when it arrives (e.g. replying to SAMpai)
  useEffect(() => {
    if (initialContent) {
      setContent(initialContent)
      setMentionQuery(null)
      // Detect if the initial content ends with a @mention query
      const q = detectMentionAtCaret(initialContent, initialContent.length)
      setMentionQuery(q)
      setTimeout(() => {
        textareaRef.current?.focus()
        const len = initialContent.length
        textareaRef.current?.setSelectionRange(len, len)
      }, 0)
      onInitialContentConsumed?.()
    }
  }, [initialContent])  // eslint-disable-line react-hooks/exhaustive-deps

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const val = e.target.value
      setContent(val)
      onTyping()

      const caret = e.target.selectionStart ?? val.length
      const q = detectMentionAtCaret(val, caret)
      setMentionQuery(q)
    },
    [onTyping]
  )

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      // Forward to autocomplete first when it's open
      if (mentionQuery !== null && autocompleteRef.current) {
        const handled = forwardKeyToMentionAutocomplete(autocompleteRef.current, e)
        if (handled) return
      }

      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault()
        if (mentionQuery !== null) return
        submit()
      }
    },
    [content, mentionQuery]  // eslint-disable-line react-hooks/exhaustive-deps
  )

  const submit = useCallback(() => {
    const trimmed = content.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setContent("")
    setMentionQuery(null)
    textareaRef.current?.focus()
  }, [content, disabled, onSend])

  const acceptMention = useCallback(
    (username: string) => {
      if (!textareaRef.current) return
      const caret = textareaRef.current.selectionStart ?? content.length
      const before = content.slice(0, caret)
      const after = content.slice(caret)
      const replaced = before.replace(/@(\w*)$/, `@${username} `) + after
      setContent(replaced)
      setMentionQuery(null)
      setTimeout(() => textareaRef.current?.focus(), 0)
    },
    [content]
  )

  return (
    <div className="relative flex items-end gap-2 px-3 py-3 border-t border-border bg-background">
      {mentionQuery !== null && (
        <MentionAutocomplete
          ref={autocompleteRef as React.Ref<HTMLDivElement>}
          query={mentionQuery}
          members={members}
          currentUserId={currentUserId}
          onSelect={acceptMention}
          onClose={() => setMentionQuery(null)}
        />
      )}

      <textarea
        ref={textareaRef}
        value={content}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder="Type a message… (@SAMpai to ask the AI)"
        rows={1}
        className="flex-1 resize-none bg-muted/50 rounded-xl px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:ring-1 focus:ring-violet-500/50 disabled:opacity-50 max-h-40 overflow-y-auto"
        style={{ lineHeight: "1.5" }}
      />

      <button
        onClick={submit}
        disabled={disabled || !content.trim()}
        className="flex-shrink-0 w-9 h-9 rounded-xl bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center transition-colors"
        aria-label="Send message"
      >
        <Send className="w-4 h-4 text-white" />
      </button>
    </div>
  )
}
