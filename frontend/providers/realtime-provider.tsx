"use client"

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useCallback,
  useReducer,
  type ReactNode,
} from "react"
import { toast } from "sonner"
import API, { WS_BASE } from "@/api/axios"
import { useRouter } from "next/navigation"

// ── Types ────────────────────────────────────────────────────────────────────

export type PendingInvite = {
  id: number
  group_chat_id: number
  inviter_id: number
  invitee_id: number
  status: string
  created_at: string
  inviter: { id: number; username: string }
  invitee: { id: number; username: string }
}

type GroupChatOut = {
  id: number
  file_id: number
  classroom_id: number
}

type ThreadListItem = {
  id: number
  file_id: number
  name: string | null
  is_archived: boolean
  unread_count: number
  last_message_preview: string | null
}

type RealtimeState = {
  pendingInvites: PendingInvite[]
  unreadByThread: Record<number, number>
}

type RealtimeAction =
  | { type: "SET_INVITES"; invites: PendingInvite[] }
  | { type: "ADD_INVITE"; invite: PendingInvite }
  | { type: "REMOVE_INVITE"; inviteId: number }
  | { type: "SET_UNREAD_MAP"; map: Record<number, number> }
  | { type: "SET_UNREAD"; threadId: number; count: number }
  | { type: "BUMP_UNREAD"; threadId: number }
  | { type: "CLEAR_UNREAD"; threadId: number }

function reducer(state: RealtimeState, action: RealtimeAction): RealtimeState {
  switch (action.type) {
    case "SET_INVITES":
      return { ...state, pendingInvites: action.invites }
    case "ADD_INVITE": {
      const already = state.pendingInvites.some((i) => i.id === action.invite.id)
      if (already) return state
      return { ...state, pendingInvites: [action.invite, ...state.pendingInvites] }
    }
    case "REMOVE_INVITE":
      return {
        ...state,
        pendingInvites: state.pendingInvites.filter((i) => i.id !== action.inviteId),
      }
    case "SET_UNREAD_MAP":
      return { ...state, unreadByThread: action.map }
    case "SET_UNREAD":
      return { ...state, unreadByThread: { ...state.unreadByThread, [action.threadId]: action.count } }
    case "BUMP_UNREAD":
      return {
        ...state,
        unreadByThread: {
          ...state.unreadByThread,
          [action.threadId]: Math.max(0, (state.unreadByThread[action.threadId] ?? 0) + 1),
        },
      }
    case "CLEAR_UNREAD": {
      const next = { ...state.unreadByThread }
      delete next[action.threadId]
      return { ...state, unreadByThread: next }
    }
    default:
      return state
  }
}

// ── Context ───────────────────────────────────────────────────────────────────

type RealtimeContextValue = {
  pendingInvites: PendingInvite[]
  unreadByThread: Record<number, number>
  acceptInvite: (inviteId: number) => Promise<GroupChatOut>
  rejectInvite: (inviteId: number) => Promise<void>
  clearUnread: (threadId: number) => void
}

const RealtimeContext = createContext<RealtimeContextValue>({
  pendingInvites: [],
  unreadByThread: {},
  acceptInvite: async () => { throw new Error("not mounted") },
  rejectInvite: async () => { throw new Error("not mounted") },
  clearUnread: () => {},
})

export function useRealtimeContext() {
  return useContext(RealtimeContext)
}

// ── Provider ──────────────────────────────────────────────────────────────────

export function RealtimeProvider({ children }: { children: ReactNode }) {
  const router = useRouter()
  const [state, dispatch] = useReducer(reducer, { pendingInvites: [], unreadByThread: {} })

  const wsRef = useRef<WebSocket | null>(null)
  const retryRef = useRef(0)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)
  // Toast IDs keyed by invite id so we can dismiss on cancel
  const toastIdsRef = useRef<Record<number, string | number>>({})

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      wsRef.current?.close()
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current)
    }
  }, [])

  const hydrate = useCallback(async () => {
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null
    if (!token) return
    try {
      const [invitesRes, threadsRes] = await Promise.all([
        API.get<PendingInvite[]>("/group-chat/invites/pending"),
        API.get<ThreadListItem[]>("/group-chat/threads"),
      ])
      dispatch({ type: "SET_INVITES", invites: invitesRes.data })

      // Seed unread counts so badges reflect activity that happened while offline
      const unreadMap: Record<number, number> = {}
      for (const t of threadsRes.data) {
        if (t.unread_count > 0) unreadMap[t.id] = t.unread_count
      }
      dispatch({ type: "SET_UNREAD_MAP", map: unreadMap })
    } catch {
      // non-fatal
    }
  }, [])

  const connect = useCallback(() => {
    if (!mountedRef.current) return
    if (typeof window === "undefined") return
    const token = localStorage.getItem("token")
    if (!token) return

    const ws = new WebSocket(`${WS_BASE}/group-chat/ws/user?token=${token}`)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) { ws.close(); return }
      retryRef.current = 0
      void hydrate()
    }

    ws.onmessage = (evt) => {
      if (!mountedRef.current) return
      let data: Record<string, unknown>
      try { data = JSON.parse(evt.data) } catch { return }

      const type = data.type as string

      if (type === "invite_new") {
        const invite = data.invite as PendingInvite
        dispatch({ type: "ADD_INVITE", invite })
        const toastId = toast(
          `${invite.inviter.username} invited you to a group chat`,
          {
            duration: 20000,
            action: {
              label: "Accept",
              onClick: () => {
                void handleAccept(invite.id)
              },
            },
            cancel: {
              label: "Decline",
              onClick: () => {
                void handleReject(invite.id)
              },
            },
          }
        )
        toastIdsRef.current[invite.id] = toastId
      }

      if (type === "invite_cancelled") {
        const inviteId = data.invite_id as number
        dispatch({ type: "REMOVE_INVITE", inviteId })
        const tid = toastIdsRef.current[inviteId]
        if (tid !== undefined) {
          toast.dismiss(tid)
          delete toastIdsRef.current[inviteId]
        }
      }

      if (type === "thread_unread_bump") {
        const threadId = data.thread_id as number
        dispatch({ type: "BUMP_UNREAD", threadId })
      }
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      scheduleReconnect()
    }
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  const scheduleReconnect = useCallback(() => {
    if (!mountedRef.current) return
    const delay = Math.min(1000 * Math.pow(2, retryRef.current), 30000)
    retryRef.current += 1
    retryTimerRef.current = setTimeout(() => {
      if (!mountedRef.current) return
      connect()
    }, delay)
  }, [connect])

  // Connect after hydration (client-side only)
  useEffect(() => {
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null
    if (!token) return
    void hydrate()
    connect()
  }, [hydrate, connect])

  // Re-connect when the user logs in (e.g. the root layout persists across
  // navigation in Next.js App Router, so the initial effect may have run
  // before the token was available)
  useEffect(() => {
    const onLogin = () => {
      if (!mountedRef.current) return
      if (retryTimerRef.current) {
        clearTimeout(retryTimerRef.current)
        retryTimerRef.current = null
      }
      retryRef.current = 0
      void hydrate()
      connect()
    }
    window.addEventListener("auth:login", onLogin)
    return () => window.removeEventListener("auth:login", onLogin)
  }, [hydrate, connect])

  const handleAccept = useCallback(async (inviteId: number): Promise<GroupChatOut> => {
    const res = await API.post<GroupChatOut>(`/group-chat/invites/${inviteId}/accept`)
    dispatch({ type: "REMOVE_INVITE", inviteId })
    const tid = toastIdsRef.current[inviteId]
    if (tid !== undefined) { toast.dismiss(tid); delete toastIdsRef.current[inviteId] }
    toast.success("Joined group chat!")
    router.push(`/classroom/${res.data.classroom_id}/group/${res.data.id}`)
    return res.data
  }, [router])

  const handleReject = useCallback(async (inviteId: number) => {
    await API.post(`/group-chat/invites/${inviteId}/reject`)
    dispatch({ type: "REMOVE_INVITE", inviteId })
  }, [])

  const clearUnread = useCallback((threadId: number) => {
    dispatch({ type: "CLEAR_UNREAD", threadId })
  }, [])

  return (
    <RealtimeContext.Provider
      value={{
        pendingInvites: state.pendingInvites,
        unreadByThread: state.unreadByThread,
        acceptInvite: handleAccept,
        rejectInvite: handleReject,
        clearUnread,
      }}
    >
      {children}
    </RealtimeContext.Provider>
  )
}
