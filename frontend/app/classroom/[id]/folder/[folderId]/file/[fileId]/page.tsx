"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { useParams, useRouter } from "next/navigation"
import dynamic from "next/dynamic"
import { motion } from "framer-motion"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import API from "@/api/axios"
import { useCurrentUser, type CurrentUser } from "@/hooks/use-current-user"
import { normalizeErrorDetail } from "@/lib/error-utils"
import { useTheme } from "@/hooks/use-theme"
import ClassroomSidebar from "@/components/classroom/sidebar"
import ClassroomHeader from "@/components/classroom/header"
import { LoadingOverlay } from "@/components/ui/liquid-orb-loader"
import { Download, Send, Loader2, AlertCircle, RefreshCw, BookOpen, BrainCircuit, Map, MessageSquare } from "lucide-react"
import { QuizPanel } from "@/components/quiz/QuizPanel"
import { FlashcardPanel } from "@/components/flashcards/FlashcardPanel"
import MindmapShell from "@/components/mindmap/mindmap-shell"
import { InviteButton } from "@/components/group-chat/invite-button"

const Plasma = dynamic(
  () => import("@/components/backgrounds/plasma").then((m) => ({ default: m.Plasma })),
  { ssr: false }
)

// ── Types ──────────────────────────────────────────────────────────────────────

type Classroom = {
  id: number
  name: string
  description: string | null
  code: string
  owner_id: number
  members: { id: number; username: string; email: string }[]
}

type Folder = { id: number; name: string; classroom_id: number }

type FileType = {
  id: number
  filename: string
  file_url: string
  file_key: string
  file_type: string | null
  file_size: number | null
  processing_status: "pending" | "processing" | "naive_ready" | "completed" | "failed"
  description: string | null
  folder_id: number
  uploaded_at: string
  processed_at: string | null
}

type ChatMessage = {
  id: number
  role: "user" | "assistant"
  content: string
  timestamp: string
}

type TabId = "chat" | "quiz" | "flashcards" | "mindmap"

// ── Sub-components ─────────────────────────────────────────────────────────────

function ThinkingDots() {
  return (
    <div className="flex justify-start px-1">
      <div className="rounded-2xl rounded-bl-sm bg-card/40 backdrop-blur-md border border-white/10 dark:border-white/10 px-4 py-3.5">
        <div className="flex gap-1.5 items-center h-4">
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="block w-1.5 h-1.5 rounded-full bg-foreground/50"
              animate={{ y: [0, -5, 0] }}
              transition={{ duration: 0.9, delay: i * 0.18, repeat: Infinity, ease: "easeInOut" }}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

const mdComponents = {
  p: ({ children }: { children: React.ReactNode }) => (
    <p className="mb-1 last:mb-0 leading-relaxed">{children}</p>
  ),
  strong: ({ children }: { children: React.ReactNode }) => (
    <strong className="font-semibold">{children}</strong>
  ),
  em: ({ children }: { children: React.ReactNode }) => <em className="italic">{children}</em>,
  ul: ({ children }: { children: React.ReactNode }) => (
    <ul className="list-disc pl-4 mb-1 space-y-0.5">{children}</ul>
  ),
  ol: ({ children }: { children: React.ReactNode }) => (
    <ol className="list-decimal pl-4 mb-1 space-y-0.5">{children}</ol>
  ),
  li: ({ children }: { children: React.ReactNode }) => <li>{children}</li>,
  code: ({ children }: { children: React.ReactNode }) => (
    <code className="bg-black/20 dark:bg-white/10 px-1 py-0.5 rounded text-xs font-mono">{children}</code>
  ),
  blockquote: ({ children }: { children: React.ReactNode }) => (
    <blockquote className="border-l-2 border-border/60 pl-3 italic text-foreground/70">{children}</blockquote>
  ),
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="text-sm text-foreground">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents as never}>
        {content}
      </ReactMarkdown>
    </div>
  )
}

function StreamingText({ text, onDone }: { text: string; onDone: () => void }) {
  const [displayed, setDisplayed] = useState("")
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone

  useEffect(() => {
    const words = text.split(" ")
    const msPerWord = Math.max(8, Math.min(35, 1600 / words.length))
    let i = 0
    const timer = setInterval(() => {
      i++
      setDisplayed(words.slice(0, i).join(" "))
      if (i >= words.length) {
        clearInterval(timer)
        onDoneRef.current()
      }
    }, msPerWord)
    return () => clearInterval(timer)
  }, [text])

  return <MarkdownContent content={displayed} />
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function FilePage() {
  const params = useParams()
  const router = useRouter()
  const classroomId = parseInt(params.id as string, 10)
  const folderId = parseInt(params.folderId as string, 10)
  const fileId = parseInt(params.fileId as string, 10)
  const { user, loading: userLoading, setUser } = useCurrentUser()
  const { theme } = useTheme()

  const [classroom, setClassroom] = useState<Classroom | null>(null)
  const [folder, setFolder] = useState<Folder | null>(null)
  const [file, setFile] = useState<FileType | null>(null)
  const [files, setFiles] = useState<FileType[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [isDownloading, setIsDownloading] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabId>("chat")

  // Chat
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [question, setQuestion] = useState("")
  const [isAsking, setIsAsking] = useState(false)
  const [chatError, setChatError] = useState<string | null>(null)
  const [freshMessageId, setFreshMessageId] = useState<number | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null)

  const plasmaColor = theme === "dark" ? "#60a5fa" : "#3b82f6"

  // ── Auth ────────────────────────────────────────────────────────────────────

  const clearAuthAndRedirect = useCallback(() => {
    if (typeof window !== "undefined") {
      localStorage.removeItem("token")
      localStorage.removeItem("user")
    }
    setUser(null as unknown as CurrentUser | null)
    router.push("/login")
  }, [router, setUser])

  // ── Data fetching ───────────────────────────────────────────────────────────

  const fetchFileData = useCallback(async () => {
    try {
      const res = await API.get<FileType>(`/files/${fileId}`)
      setFile(res.data)
      return res.data
    } catch (err: unknown) {
      if ((err as { response?: { status?: number } })?.response?.status === 401) clearAuthAndRedirect()
      return null
    }
  }, [fileId, clearAuthAndRedirect])

  const fetchHistory = useCallback(async () => {
    try {
      const res = await API.get<{ messages: ChatMessage[] }>(
        `/chat/files/${fileId}/history?limit=100&offset=0`
      )
      setMessages(res.data.messages)
    } catch {
      // non-fatal
    }
  }, [fileId])

  const startPolling = useCallback(() => {
    if (pollIntervalRef.current) return
    pollIntervalRef.current = setInterval(async () => {
      const updated = await fetchFileData()
      if (updated && (updated.processing_status === "completed" || updated.processing_status === "failed")) {
        clearInterval(pollIntervalRef.current!)
        pollIntervalRef.current = null
        if (updated.processing_status === "completed") await fetchHistory()
      }
    }, 3000)
  }, [fetchFileData, fetchHistory])

  useEffect(() => () => { if (pollIntervalRef.current) clearInterval(pollIntervalRef.current) }, [])

  useEffect(() => {
    if (userLoading) return
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null
    if (!user || !token) { router.push("/login"); return }
    if (!classroomId || !folderId || !fileId) return

    const load = async () => {
      try {
        const [clsRes, foldersRes, fileRes, filesRes] = await Promise.all([
          API.get<Classroom>(`/classrooms/${classroomId}`),
          API.get<Folder[]>(`/folders/classroom/${classroomId}`),
          API.get<FileType>(`/files/${fileId}`),
          API.get<FileType[]>(`/files/folder/${folderId}`),
        ])
        setClassroom(clsRes.data)
        setFolder(foldersRes.data.find((f) => f.id === folderId) ?? null)
        const f = fileRes.data
        setFile(f)
        setFiles(filesRes.data)
        if (f.processing_status === "completed" || f.processing_status === "naive_ready") {
          await fetchHistory()
        }
        if (f.processing_status === "pending" || f.processing_status === "processing" || f.processing_status === "naive_ready") {
          startPolling()
        }
      } catch (err: unknown) {
        const status = (err as { response?: { status?: number } })?.response?.status
        if (status === 401) clearAuthAndRedirect()
        else if (status === 403) setError("You are not a member of this classroom")
        else setError("Failed to load. Please try again.")
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [userLoading, user, classroomId, folderId, fileId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, isAsking])

  // ── Actions ─────────────────────────────────────────────────────────────────

  const handleAsk = async () => {
    if (!question.trim() || isAsking || !canChat) return
    const q = question.trim()
    setQuestion("")
    setChatError(null)
    setIsAsking(true)
    setFreshMessageId(null)

    const tempId = Date.now()
    setMessages((prev) => [...prev, { id: tempId, role: "user", content: q, timestamp: new Date().toISOString() }])

    try {
      const res = await API.post<{ answer: string; message_id: number }>(`/chat/files/${fileId}/ask`, { question: q })
      const newId = res.data.message_id
      setMessages((prev) => [
        ...prev,
        { id: newId, role: "assistant", content: res.data.answer, timestamp: new Date().toISOString() },
      ])
      setFreshMessageId(newId)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setChatError(normalizeErrorDetail(detail, "Failed to get an answer. Please try again."))
      setMessages((prev) => prev.filter((m) => m.id !== tempId))
    } finally {
      setIsAsking(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleAsk() }
  }

  const handleDownload = async () => {
    if (!fileId || isDownloading) return
    setActionError(null)
    setIsDownloading(true)
    try {
      const res = await API.get<{ download_url: string }>(`/files/${fileId}/download`)
      if (res.data?.download_url) window.open(res.data.download_url, "_blank")
      else setActionError("Failed to get download link.")
    } catch (err: unknown) {
      setActionError(normalizeErrorDetail((err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail, "Failed to download."))
    } finally {
      setIsDownloading(false)
    }
  }

  const handleReprocess = async () => {
    try {
      await API.post(`/files/${fileId}/reprocess`)
      setFile((prev) => prev ? { ...prev, processing_status: "pending", description: null } : prev)
      setMessages([])
      startPolling()
    } catch (err: unknown) {
      setActionError(normalizeErrorDetail((err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail, "Failed to start reprocessing."))
    }
  }

  // ── Derived ─────────────────────────────────────────────────────────────────

  const isOwner = user && classroom && user.id === classroom.owner_id
  const status = file?.processing_status ?? "pending"
  const isCompleted = status === "completed"
  const isNaiveReady = status === "naive_ready"
  const isFailed = status === "failed"
  const isInProgress = status === "pending" || status === "processing"
  const naiveReady = isNaiveReady || isCompleted
  const fullReady = isCompleted
  const canChat = naiveReady

  // ── Loading / error ──────────────────────────────────────────────────────────

  if (loading || userLoading) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <LoadingOverlay isLoading progress={0} message="Loading file…" size="xl" fullScreen />
      </div>
    )
  }

  if (error || !classroom || !folder || !file) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-destructive">{error || "File not found"}</p>
          <button onClick={() => router.push(`/classroom/${classroomId}/folder/${folderId}`)}
            className="px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer">
            Back to Folder
          </button>
        </div>
      </div>
    )
  }

  // Summary injected as synthetic first assistant message
  const summaryMessage: ChatMessage | null = file.description
    ? { id: -1, role: "assistant", content: file.description, timestamp: file.uploaded_at }
    : null

  // ── Tab config ───────────────────────────────────────────────────────────────

  const tabs: { id: TabId; label: string; icon: React.ReactNode; disabled?: boolean; loading?: boolean }[] = [
    { id: "chat", label: "Chat", icon: <MessageSquare className="h-3.5 w-3.5" /> },
    { id: "quiz", label: "Quiz", icon: <BookOpen className="h-3.5 w-3.5" />, disabled: !fullReady, loading: isNaiveReady },
    { id: "flashcards", label: "Flashcards", icon: <BrainCircuit className="h-3.5 w-3.5" /> },
    { id: "mindmap", label: "Mindmap", icon: <Map className="h-3.5 w-3.5" />, disabled: !fullReady, loading: isNaiveReady },
  ]

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="relative min-h-screen w-full overflow-x-hidden bg-background">

      {/* Plasma — fixed, behind everything */}
      <div className="fixed inset-0 z-0 pointer-events-none">
        <Plasma
          color={plasmaColor}
          speed={0.35}
          direction="forward"
          scale={1.15}
          opacity={theme === "dark" ? 0.45 : 0.3}
          mouseInteractive={false}
        />
      </div>

      <ClassroomHeader
        classroomName={classroom.name}
        folderName={folder.name}
        fileName={file.filename}
        classroomId={classroomId}
        folderId={folderId}
        username={user?.username ?? ""}
        onMenuClick={() => setSidebarCollapsed(!sidebarCollapsed)}
        onLogout={() => {
          if (typeof window !== "undefined") { localStorage.removeItem("token"); localStorage.removeItem("user") }
          setUser(null as unknown as CurrentUser | null)
          router.push("/login")
        }}
      />

      <div className="flex pt-16">
        <ClassroomSidebar
          collapsed={sidebarCollapsed}
          currentClassroomId={classroomId}
          mode="file"
          folderId={folderId}
          files={files}
          currentFileId={fileId}
          onFolderClick={() => router.push(`/classroom/${classroomId}/folder/${folderId}`)}
          onFileSelect={(fid) => router.push(`/classroom/${classroomId}/folder/${folderId}/file/${fid}`)}
          onHomeClick={() => router.push(isOwner ? "/created" : "/joined")}
        />

        <main className={`relative z-10 flex-1 flex flex-col h-[calc(100vh-4rem)] transition-all duration-300 ${sidebarCollapsed ? "ml-0" : "ml-[280px]"}`}>

          {/* ── Top bar: tabs + action buttons ── */}
          <div className="shrink-0 flex items-center justify-between gap-3 px-4 pt-3 pb-2">

            {/* Tab pills */}
            <div className="flex items-center gap-1 bg-card/30 backdrop-blur-md border border-border/40 rounded-full p-1">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  disabled={tab.disabled}
                  onClick={() => {
                    if (tab.disabled) return
                    if (tab.id === "mindmap") setSidebarCollapsed(true)
                    setActiveTab(tab.id)
                  }}
                  title={tab.disabled ? "Available once full analysis finishes" : undefined}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer disabled:cursor-not-allowed ${
                    activeTab === tab.id
                      ? "bg-card/80 border border-border/60 text-foreground shadow-sm"
                      : tab.disabled
                      ? "text-muted-foreground/40"
                      : "text-muted-foreground hover:text-foreground hover:bg-card/40"
                  }`}
                >
                  {tab.loading ? <Loader2 className="h-3 w-3 animate-spin opacity-60" /> : tab.icon}
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Action buttons */}
            <div className="flex items-center gap-2 shrink-0">
              {actionError && (
                <span className="text-xs text-destructive max-w-[160px] truncate">{actionError}</span>
              )}
              {isFailed && (
                <button onClick={handleReprocess}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-destructive/10 border border-destructive/30 text-destructive hover:bg-destructive/20 cursor-pointer transition-colors">
                  <RefreshCw className="h-3 w-3" /> Retry
                </button>
              )}
              {isInProgress && (
                <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs text-amber-500 dark:text-amber-400 bg-amber-500/10 border border-amber-500/20">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  {status === "processing" ? "Processing…" : "Queued…"}
                </span>
              )}
              <InviteButton fileId={fileId} classroomId={classroomId} />
              <button type="button" onClick={handleDownload} disabled={isDownloading}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-card/50 backdrop-blur-sm border border-border/50 text-foreground hover:bg-card/70 disabled:opacity-50 cursor-pointer transition-colors">
                {isDownloading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}
                {isDownloading ? "Preparing…" : "Download"}
              </button>
            </div>
          </div>

          {/* ── Tab content panels ── */}
          <div className="flex-1 min-h-0 px-4 pb-4">

            {/* ── CHAT ── */}
            <div className={`h-full flex flex-col gap-3 ${activeTab === "chat" ? "flex" : "hidden"}`}>

              {/* Messages */}
              <div className="flex-1 min-h-0 overflow-y-auto space-y-3 py-2 px-1">

                {/* Summary as first AI message */}
                {summaryMessage && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.35 }}
                    className="flex justify-start"
                  >
                    <div className="max-w-[82%] rounded-2xl rounded-bl-sm bg-card/40 backdrop-blur-md border border-white/10 dark:border-white/10 px-4 py-3">
                      <MarkdownContent content={summaryMessage.content} />
                    </div>
                  </motion.div>
                )}

                {/* Empty state (no summary, no messages) */}
                {!summaryMessage && messages.length === 0 && (
                  <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
                    {isFailed ? (
                      <>
                        <AlertCircle className="h-6 w-6 text-destructive" />
                        <p className="text-sm text-destructive">Processing failed.</p>
                        <button onClick={handleReprocess}
                          className="inline-flex items-center gap-1.5 rounded-full bg-destructive/10 border border-destructive/30 px-4 py-2 text-sm font-medium text-destructive hover:bg-destructive/20 cursor-pointer">
                          <RefreshCw className="h-3.5 w-3.5" /> Retry
                        </button>
                      </>
                    ) : isInProgress ? (
                      <>
                        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                        <p className="text-sm text-muted-foreground">Processing document…</p>
                        <p className="text-xs text-muted-foreground/60">Large files may take 2–5 minutes.</p>
                      </>
                    ) : (
                      <p className="text-sm text-muted-foreground">Ask anything about this document.</p>
                    )}
                  </div>
                )}

                {/* Chat history */}
                {messages.map((msg) => (
                  <motion.div
                    key={msg.id}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.25 }}
                    className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    {msg.role === "user" ? (
                      <div className="max-w-[82%] rounded-2xl rounded-br-sm bg-chart-1/25 backdrop-blur-md border border-chart-1/20 px-4 py-3">
                        <p className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                      </div>
                    ) : (
                      <div className="max-w-[82%] rounded-2xl rounded-bl-sm bg-card/40 backdrop-blur-md border border-white/10 dark:border-white/10 px-4 py-3">
                        {msg.id === freshMessageId ? (
                          <StreamingText text={msg.content} onDone={() => setFreshMessageId(null)} />
                        ) : (
                          <MarkdownContent content={msg.content} />
                        )}
                      </div>
                    )}
                  </motion.div>
                ))}

                {isAsking && <ThinkingDots />}

                {chatError && (
                  <p className="text-center text-xs text-destructive">{chatError}</p>
                )}

                <div ref={messagesEndRef} />
              </div>

              {/* Input bar */}
              <div className="shrink-0">
                <div className="flex items-end gap-2 bg-card/30 backdrop-blur-md border border-border/40 rounded-2xl p-2">
                  <textarea
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={handleKeyDown}
                    disabled={isAsking || !canChat}
                    placeholder={
                      isFailed ? "Processing failed — click Retry"
                      : isInProgress ? "Processing document, check back shortly…"
                      : "Ask a question… (Enter to send, Shift+Enter for new line)"
                    }
                    rows={1}
                    className="flex-1 resize-none bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none disabled:opacity-40 disabled:cursor-not-allowed max-h-32 overflow-y-auto"
                    style={{ fieldSizing: "content" } as React.CSSProperties}
                  />
                  <button
                    type="button"
                    onClick={handleAsk}
                    disabled={!question.trim() || isAsking || !canChat}
                    className="shrink-0 flex items-center justify-center rounded-xl bg-chart-1/80 hover:bg-chart-1 w-9 h-9 text-white disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
                  >
                    {isAsking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  </button>
                </div>
                <p className="mt-1 text-[11px] text-muted-foreground/50 px-2">
                  {canChat ? "Enter · send  ·  Shift+Enter · new line" : isInProgress ? "Processing in background…" : ""}
                </p>
              </div>
            </div>

            {/* ── QUIZ ── */}
            <div className={`h-full rounded-2xl border border-border/40 bg-card/30 backdrop-blur-md overflow-hidden ${activeTab === "quiz" ? "flex flex-col" : "hidden"}`}>
              <QuizPanel fileId={Number(fileId)} canQuiz={fullReady} />
            </div>

            {/* ── FLASHCARDS ── */}
            <div className={`h-full rounded-2xl border border-border/40 bg-card/30 backdrop-blur-md overflow-hidden ${activeTab === "flashcards" ? "flex flex-col" : "hidden"}`}>
              <FlashcardPanel fileId={Number(fileId)} canFlashcard={naiveReady} />
            </div>

            {/* ── MINDMAP ── */}
            <div className={`h-full rounded-2xl border border-border/40 bg-card/30 backdrop-blur-md overflow-hidden ${activeTab === "mindmap" ? "flex flex-col" : "hidden"}`}>
              {fullReady ? (
                <MindmapShell fileId={Number(fileId)} classroomId={classroomId} fileName={file.filename} isActive={activeTab === "mindmap"} />
              ) : (
                <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                  Mindmap will be available once full document analysis finishes.
                </div>
              )}
            </div>

          </div>
        </main>
      </div>
    </div>
  )
}
