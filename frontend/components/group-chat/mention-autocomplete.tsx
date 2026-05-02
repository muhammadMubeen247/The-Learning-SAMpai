"use client"

import { useEffect, useRef, useState, forwardRef } from "react"

type Member = {
  user_id: number
  username: string
}

type Props = {
  query: string
  members: Member[]
  currentUserId?: number
  onSelect: (username: string) => void
  onClose: () => void
}

export const MentionAutocomplete = forwardRef<HTMLDivElement, Props>(
  function MentionAutocomplete({ query, members, currentUserId, onSelect, onClose }, forwardedRef) {
    const innerRef = useRef<HTMLDivElement>(null)
    const ref = (forwardedRef as React.RefObject<HTMLDivElement>) ?? innerRef
    const [selectedIndex, setSelectedIndex] = useState(0)

    const sampai: Member = { user_id: 0, username: "SAMpai" }
    const filtered = members
      .filter(
        (m) =>
          m.username.toLowerCase().startsWith(query.toLowerCase()) &&
          m.username.toLowerCase() !== "sampai" &&
          (currentUserId === undefined || m.user_id !== currentUserId)
      )
      .concat(
        "sampai".startsWith(query.toLowerCase()) || query === "" ? [sampai] : []
      )

    useEffect(() => {
      setSelectedIndex(0)
    }, [query])

    useEffect(() => {
      const handle = (e: MouseEvent) => {
        if (ref.current && !ref.current.contains(e.target as Node)) onClose()
      }
      document.addEventListener("mousedown", handle)
      return () => document.removeEventListener("mousedown", handle)
    }, [onClose, ref])

    const handleKeyboard = (e: React.KeyboardEvent): boolean => {
      if (filtered.length === 0) return false
      if (e.key === "ArrowDown") {
        e.preventDefault()
        setSelectedIndex((i) => (i + 1) % filtered.length)
        return true
      }
      if (e.key === "ArrowUp") {
        e.preventDefault()
        setSelectedIndex((i) => (i - 1 + filtered.length) % filtered.length)
        return true
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault()
        onSelect(filtered[selectedIndex]?.username ?? "")
        return true
      }
      if (e.key === "Escape") {
        onClose()
        return true
      }
      return false
    }

    // Store latest closure on the DOM element so the composer can call it
    useEffect(() => {
      if (ref.current) {
        (ref.current as HTMLDivElement & { __mentionKeyHandler?: typeof handleKeyboard }).__mentionKeyHandler = handleKeyboard
      }
    })

    if (filtered.length === 0) return null

    return (
      <div
        ref={ref as React.Ref<HTMLDivElement>}
        className="absolute bottom-full left-0 mb-1 w-56 bg-popover border border-border rounded-lg shadow-lg z-50 overflow-hidden"
      >
        {filtered.map((m, idx) => (
          <button
            key={m.user_id}
            onMouseDown={(e) => {
              e.preventDefault()
              onSelect(m.username)
            }}
            onMouseEnter={() => setSelectedIndex(idx)}
            className={`w-full text-left px-3 py-2 text-sm transition-colors flex items-center gap-2 ${
              idx === selectedIndex ? "bg-muted" : "hover:bg-muted/60"
            } ${m.username === "SAMpai" ? "text-violet-400 font-medium" : "text-foreground"}`}
          >
            <span
              className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold text-white ${
                m.username === "SAMpai" ? "bg-violet-600" : "bg-slate-600"
              }`}
            >
              {m.username[0].toUpperCase()}
            </span>
            @{m.username}
          </button>
        ))}
      </div>
    )
  }
)

export function forwardKeyToMentionAutocomplete(
  el: HTMLDivElement | null,
  e: React.KeyboardEvent
): boolean {
  if (!el) return false
  const handler = (el as HTMLDivElement & { __mentionKeyHandler?: (e: React.KeyboardEvent) => boolean }).__mentionKeyHandler
  return handler ? handler(e) : false
}
