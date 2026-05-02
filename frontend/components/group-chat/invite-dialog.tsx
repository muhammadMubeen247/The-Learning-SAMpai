"use client"

import { useState, useEffect, useCallback } from "react"
import { X, Search, Users, Loader2 } from "lucide-react"
import API from "@/api/axios"
import { toast } from "sonner"

type EligibleUser = {
  id: number
  username: string
}

type ThreadOption = {
  id: number
  name: string | null
  file_id: number
}

type Props = {
  fileId: number
  onClose: () => void
}

export function InviteDialog({ fileId, onClose }: Props) {
  const [eligible, setEligible] = useState<EligibleUser[]>([])
  const [existingThreads, setExistingThreads] = useState<ThreadOption[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [targetThreadId, setTargetThreadId] = useState<number | null>(null)
  const [search, setSearch] = useState("")
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    const load = async () => {
      try {
        const [eligRes, threadsRes] = await Promise.all([
          API.get<EligibleUser[]>(`/group-chat/files/${fileId}/eligible-invitees`),
          API.get<ThreadOption[]>("/group-chat/threads"),
        ])
        setEligible(eligRes.data)
        setExistingThreads(threadsRes.data.filter((t) => t.file_id === fileId))
      } catch {
        toast.error("Failed to load invite options.")
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [fileId])

  const filtered = eligible.filter((u) =>
    u.username.toLowerCase().includes(search.toLowerCase())
  )

  const toggle = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleSend = useCallback(async () => {
    if (selectedIds.size === 0) return
    setSending(true)
    try {
      await API.post(`/group-chat/files/${fileId}/invite`, {
        user_ids: Array.from(selectedIds),
        group_chat_id: targetThreadId ?? undefined,
      })
      toast.success(`Invite${selectedIds.size > 1 ? "s" : ""} sent!`)
      onClose()
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 409) {
        toast.error("Some users are already members.")
      } else {
        toast.error("Failed to send invites.")
      }
    } finally {
      setSending(false)
    }
  }, [selectedIds, fileId, targetThreadId, onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-background/60 backdrop-blur-sm" onClick={onClose} />

      <div className="relative w-full max-w-md bg-card border border-border rounded-2xl shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-violet-400" />
            <h2 className="font-semibold text-sm">Invite to Group Chat</h2>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-md hover:bg-muted transition-colors cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {/* Existing thread picker */}
          {existingThreads.length > 0 && (
            <div>
              <p className="text-xs text-muted-foreground mb-2">Add to existing group (optional)</p>
              <div className="space-y-1">
                <button
                  onClick={() => setTargetThreadId(null)}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                    targetThreadId === null ? "bg-violet-600/20 border border-violet-500/40 text-violet-300" : "hover:bg-muted"
                  }`}
                >
                  Create new group
                </button>
                {existingThreads.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setTargetThreadId(t.id)}
                    className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors truncate ${
                      targetThreadId === t.id ? "bg-violet-600/20 border border-violet-500/40 text-violet-300" : "hover:bg-muted"
                    }`}
                  >
                    {t.name ?? `Group #${t.id}`}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search classmates…"
              className="w-full pl-9 pr-3 py-2 bg-muted/50 rounded-lg text-sm outline-none focus:ring-1 focus:ring-violet-500/50"
            />
          </div>

          {/* Member list */}
          <div className="max-h-48 overflow-y-auto space-y-1">
            {loading ? (
              <div className="flex justify-center py-6">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : filtered.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                {eligible.length === 0 ? "No eligible classmates to invite." : "No matches."}
              </p>
            ) : (
              filtered.map((u) => (
                <label
                  key={u.id}
                  className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-muted cursor-pointer transition-colors"
                >
                  <input
                    type="checkbox"
                    checked={selectedIds.has(u.id)}
                    onChange={() => toggle(u.id)}
                    className="accent-violet-600 w-4 h-4 cursor-pointer"
                  />
                  <span
                    className="w-7 h-7 rounded-full bg-slate-600 flex items-center justify-center text-xs font-bold text-white shrink-0"
                  >
                    {u.username[0].toUpperCase()}
                  </span>
                  <span className="text-sm">{u.username}</span>
                </label>
              ))
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between pt-2 border-t border-border">
            <span className="text-xs text-muted-foreground">
              {selectedIds.size} selected
            </span>
            <div className="flex gap-2">
              <button
                onClick={onClose}
                className="px-4 py-2 rounded-lg border border-border text-sm hover:bg-muted transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={() => void handleSend()}
                disabled={selectedIds.size === 0 || sending}
                className="px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors cursor-pointer flex items-center gap-1.5"
              >
                {sending && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                Send Invite{selectedIds.size !== 1 ? "s" : ""}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
