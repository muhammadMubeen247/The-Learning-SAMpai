"use client"

import { useEffect, useRef, useCallback, useReducer } from "react"
import API, { WS_BASE } from "@/api/axios"

// ── Types ────────────────────────────────────────────────────────────────────

export type MessageRole = "user" | "agent" | "system"

export type GroupMessage = {
  id: number | string   // string for optimistic temp messages ("temp:uuid")
  group_chat_id: number
  seq: number
  user_id: number | null
  role: MessageRole
  content: string
  mentions: Array<{ kind: string; username: string }>
  reply_to_id: number | null
  is_discarded: boolean
  discard_reason: string | null
  client_msg_id: string | null
  created_at: string
  author: { id: number; username: string } | null
}

export type TypingState = {
  userId: number
  username: string
  isTyping: boolean
}

export type AgentTyping = boolean

type WsEvent =
  | { type: "message_new"; v: 1; message: GroupMessage }
  | { type: "message_discarded"; v: 1; message_id: number; reason: string }
  | { type: "agent_typing"; v: 1; thread_id: number; is_typing: boolean }
  | { type: "typing"; v: 1; thread_id: number; user_id: number; username: string; is_typing: boolean }
  | { type: "presence"; v: 1; thread_id: number; online_user_ids: number[] }
  | { type: "read_receipt"; v: 1; thread_id: number; user_id: number; last_seq: number }
  | { type: "member_joined"; v: 1; thread_id: number; user_id: number; username: string }
  | { type: "member_left"; v: 1; thread_id: number; user_id: number }

// ── Reducer ──────────────────────────────────────────────────────────────────

type State = {
  messages: GroupMessage[]
  typingUsers: TypingState[]
  agentTyping: boolean
  onlineUserIds: number[]
  readSeqs: Record<number, number>
  connected: boolean
  hasMore: boolean   // whether older messages exist to load
  loadingMore: boolean
}

type Action =
  | { type: "SET_MESSAGES"; messages: GroupMessage[] }
  | { type: "PREPEND_MESSAGES"; messages: GroupMessage[] }   // older messages loaded at top
  | { type: "UPSERT_MESSAGE"; message: GroupMessage }
  | { type: "REPLACE_TEMP"; clientMsgId: string; message: GroupMessage }
  | { type: "DISCARD_MESSAGE"; messageId: number; reason: string }
  | { type: "SET_AGENT_TYPING"; isTyping: boolean }
  | { type: "SET_USER_TYPING"; userId: number; username: string; isTyping: boolean }
  | { type: "SET_PRESENCE"; onlineUserIds: number[] }
  | { type: "SET_READ_SEQ"; userId: number; lastSeq: number }
  | { type: "SET_CONNECTED"; connected: boolean }
  | { type: "SET_HAS_MORE"; hasMore: boolean }
  | { type: "SET_LOADING_MORE"; loading: boolean }

const PAGE_SIZE = 50

function mergeMessages(existing: GroupMessage[], incoming: GroupMessage[]): GroupMessage[] {
  const map = new Map<string | number, GroupMessage>()

  for (const m of existing) {
    map.set(m.id, m)
  }

  for (const m of incoming) {
    if (m.client_msg_id) {
      const tempKey = `temp:${m.client_msg_id}`
      if (map.has(tempKey)) {
        map.delete(tempKey)
      }
    }
    map.set(m.id, m)
  }

  return Array.from(map.values()).sort((a, b) => {
    const seqA = typeof a.seq === "number" ? a.seq : -1
    const seqB = typeof b.seq === "number" ? b.seq : -1
    if (seqA !== seqB) return seqA - seqB
    return String(a.id).localeCompare(String(b.id))
  })
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "SET_MESSAGES":
      return {
        ...state,
        messages: mergeMessages(state.messages, action.messages),
        hasMore: action.messages.length >= PAGE_SIZE,
      }

    case "PREPEND_MESSAGES": {
      const merged = mergeMessages(action.messages, state.messages)
      return {
        ...state,
        messages: merged,
        hasMore: action.messages.length >= PAGE_SIZE,
        loadingMore: false,
      }
    }

    case "UPSERT_MESSAGE":
      return { ...state, messages: mergeMessages(state.messages, [action.message]) }

    case "REPLACE_TEMP": {
      const withoutTemp = state.messages.filter(
        (m) => m.id !== `temp:${action.clientMsgId}`
      )
      return { ...state, messages: mergeMessages(withoutTemp, [action.message]) }
    }

    case "DISCARD_MESSAGE":
      return {
        ...state,
        messages: state.messages.map((m) =>
          m.id === action.messageId
            ? { ...m, is_discarded: true, discard_reason: action.reason }
            : m
        ),
      }

    case "SET_AGENT_TYPING":
      return { ...state, agentTyping: action.isTyping }

    case "SET_USER_TYPING": {
      const others = state.typingUsers.filter((t) => t.userId !== action.userId)
      if (!action.isTyping) return { ...state, typingUsers: others }
      return {
        ...state,
        typingUsers: [...others, { userId: action.userId, username: action.username, isTyping: true }],
      }
    }

    case "SET_PRESENCE":
      return { ...state, onlineUserIds: action.onlineUserIds }

    case "SET_READ_SEQ":
      return {
        ...state,
        readSeqs: { ...state.readSeqs, [action.userId]: action.lastSeq },
      }

    case "SET_CONNECTED":
      return { ...state, connected: action.connected }

    case "SET_HAS_MORE":
      return { ...state, hasMore: action.hasMore }

    case "SET_LOADING_MORE":
      return { ...state, loadingMore: action.loading }

    default:
      return state
  }
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useGroupChatSocket(groupChatId: number | null) {
  const [state, dispatch] = useReducer(reducer, {
    messages: [],
    typingUsers: [],
    agentTyping: false,
    onlineUserIds: [],
    readSeqs: {},
    connected: false,
    hasMore: false,
    loadingMore: false,
  })

  const wsRef = useRef<WebSocket | null>(null)
  const retryRef = useRef(0)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)
  const groupChatIdRef = useRef(groupChatId)
  const typingTimersRef = useRef<Record<number, ReturnType<typeof setTimeout>>>({})
  const messagesRef = useRef(state.messages)

  useEffect(() => {
    messagesRef.current = state.messages
  }, [state.messages])

  useEffect(() => {
    groupChatIdRef.current = groupChatId
  }, [groupChatId])

  // Initial fetch of the most recent PAGE_SIZE messages
  const fetchLatest = useCallback(async () => {
    if (!groupChatIdRef.current) return
    try {
      const res = await API.get<GroupMessage[]>(
        `/group-chat/threads/${groupChatIdRef.current}/messages`,
        { params: { limit: PAGE_SIZE } }
      )
      dispatch({ type: "SET_MESSAGES", messages: res.data })
    } catch {
      // silent — retry on reconnect
    }
  }, [])

  // Gap-fill on reconnect: fetch messages newer than our last known seq
  const gapFill = useCallback(async () => {
    if (!groupChatIdRef.current) return
    const msgs = messagesRef.current
    const maxSeq = msgs.reduce((max, m) => {
      const s = typeof m.seq === "number" ? m.seq : 0
      return s > max ? s : max
    }, 0)
    if (maxSeq === 0) return
    try {
      // Fetch all messages after maxSeq (no before_seq means newest, so we just
      // re-fetch latest and merge — the reducer deduplicates by id)
      const res = await API.get<GroupMessage[]>(
        `/group-chat/threads/${groupChatIdRef.current}/messages`,
        { params: { limit: PAGE_SIZE } }
      )
      dispatch({ type: "SET_MESSAGES", messages: res.data })
    } catch {
      // silent
    }
  }, [])

  // Load older messages (infinite scroll — triggered by user scrolling to top)
  const loadMore = useCallback(async () => {
    if (!groupChatIdRef.current) return
    const msgs = messagesRef.current
    const minSeq = msgs.reduce((min, m) => {
      const s = typeof m.seq === "number" && m.seq > 0 ? m.seq : Infinity
      return s < min ? s : min
    }, Infinity)
    if (minSeq === Infinity) return

    dispatch({ type: "SET_LOADING_MORE", loading: true })
    try {
      const res = await API.get<GroupMessage[]>(
        `/group-chat/threads/${groupChatIdRef.current}/messages`,
        { params: { limit: PAGE_SIZE, before_seq: minSeq } }
      )
      dispatch({ type: "PREPEND_MESSAGES", messages: res.data })
    } catch {
      dispatch({ type: "SET_LOADING_MORE", loading: false })
    }
  }, [])

  const connect = useCallback(() => {
    if (!groupChatIdRef.current || !mountedRef.current) return
    if (typeof window === "undefined") return

    const token = localStorage.getItem("token")
    if (!token) return

    const url = `${WS_BASE}/group-chat/ws/group-chat/${groupChatIdRef.current}?token=${token}`
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) { ws.close(); return }
      retryRef.current = 0
      dispatch({ type: "SET_CONNECTED", connected: true })
    }

    ws.onmessage = (evt) => {
      if (!mountedRef.current) return
      let data: WsEvent
      try {
        data = JSON.parse(evt.data)
      } catch {
        return
      }

      switch (data.type) {
        case "message_new":
          dispatch({ type: "UPSERT_MESSAGE", message: data.message })
          break

        case "message_discarded":
          dispatch({ type: "DISCARD_MESSAGE", messageId: data.message_id, reason: data.reason })
          break

        case "agent_typing":
          dispatch({ type: "SET_AGENT_TYPING", isTyping: data.is_typing })
          break

        case "typing": {
          const uid = data.user_id
          const username = data.username || String(uid)
          dispatch({ type: "SET_USER_TYPING", userId: uid, username, isTyping: data.is_typing })
          if (data.is_typing) {
            clearTimeout(typingTimersRef.current[uid])
            typingTimersRef.current[uid] = setTimeout(() => {
              dispatch({ type: "SET_USER_TYPING", userId: uid, username, isTyping: false })
            }, 4000)
          }
          break
        }

        case "presence":
          dispatch({ type: "SET_PRESENCE", onlineUserIds: data.online_user_ids })
          break

        case "read_receipt":
          dispatch({ type: "SET_READ_SEQ", userId: data.user_id, lastSeq: data.last_seq })
          break
      }
    }

    ws.onerror = () => {
      // handled in onclose
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      dispatch({ type: "SET_CONNECTED", connected: false })
      scheduleReconnect()
    }
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const scheduleReconnect = useCallback(() => {
    if (!mountedRef.current) return
    const delay = Math.min(1000 * Math.pow(2, retryRef.current), 30000)
    retryRef.current += 1
    retryTimerRef.current = setTimeout(() => {
      if (!mountedRef.current) return
      void gapFill()
      connect()
    }, delay)
  }, [connect, gapFill])

  // Initial load + connect
  useEffect(() => {
    if (!groupChatId) return
    mountedRef.current = true

    void fetchLatest()
    connect()

    return () => {
      mountedRef.current = false
      wsRef.current?.close()
      wsRef.current = null
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current)
    }
  }, [groupChatId])  // eslint-disable-line react-hooks/exhaustive-deps

  // Send a message via HTTP (optimistic insert)
  const send = useCallback(
    async (content: string, replyToId?: number): Promise<GroupMessage> => {
      if (!groupChatIdRef.current) throw new Error("No group chat")
      const clientMsgId = crypto.randomUUID()

      const optimistic: GroupMessage = {
        id: `temp:${clientMsgId}`,
        group_chat_id: groupChatIdRef.current,
        seq: -1,
        user_id: null,
        role: "user",
        content,
        mentions: [],
        reply_to_id: replyToId ?? null,
        is_discarded: false,
        discard_reason: null,
        client_msg_id: clientMsgId,
        created_at: new Date().toISOString(),
        author: null,
      }
      dispatch({ type: "UPSERT_MESSAGE", message: optimistic })

      const res = await API.post<GroupMessage>(
        `/group-chat/threads/${groupChatIdRef.current}/messages`,
        { content, reply_to_id: replyToId ?? null, client_msg_id: clientMsgId }
      )
      dispatch({ type: "REPLACE_TEMP", clientMsgId, message: res.data })
      return res.data
    },
    []
  )

  const sendTypingRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const sendTyping = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    wsRef.current.send(JSON.stringify({ type: "typing", is_typing: true }))
    if (sendTypingRef.current) clearTimeout(sendTypingRef.current)
    sendTypingRef.current = setTimeout(() => {
      wsRef.current?.send(JSON.stringify({ type: "typing", is_typing: false }))
    }, 3000)
  }, [])

  const sendReadReceipt = useCallback((lastSeq: number) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    wsRef.current.send(JSON.stringify({ type: "read_receipt", last_seq: lastSeq }))
  }, [])

  return {
    messages: state.messages,
    typingUsers: state.typingUsers,
    agentTyping: state.agentTyping,
    onlineUserIds: state.onlineUserIds,
    readSeqs: state.readSeqs,
    connected: state.connected,
    hasMore: state.hasMore,
    loadingMore: state.loadingMore,
    send,
    sendTyping,
    sendReadReceipt,
    loadMore,
  }
}
