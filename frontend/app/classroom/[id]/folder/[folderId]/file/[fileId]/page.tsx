"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { useParams, useRouter } from "next/navigation"
import dynamic from "next/dynamic"
import API from "@/api/axios"
import { useCurrentUser, type CurrentUser } from "@/hooks/use-current-user"
import { normalizeErrorDetail } from "@/lib/error-utils"
import { useTheme } from "@/hooks/use-theme"
import ClassroomSidebar from "@/components/classroom/sidebar"
import ClassroomHeader from "@/components/classroom/header"
import { LoadingOverlay } from "@/components/ui/liquid-orb-loader"
import { Download, Send, Loader2, FileText, CheckCircle2, Clock, AlertCircle, RefreshCw } from "lucide-react"

const Squares = dynamic(() => import("@/components/backgrounds/squares"), { ssr: false })

// ── Types ─────────────────────────────────────────────────────────────────────

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
  processing_status: "pending" | "processing" | "completed" | "failed"
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

// ── Component ─────────────────────────────────────────────────────────────────

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

  // Chat
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [question, setQuestion] = useState("")
  const [isAsking, setIsAsking] = useState(false)
  const [chatError, setChatError] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Polling when file is still processing
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null)

  const borderColor = theme === "dark" ? "rgba(147, 197, 253, 0.3)" : "rgba(56, 189, 248, 0.4)"
  const hoverFillColor = theme === "dark" ? "rgba(147, 197, 253, 0.1)" : "rgba(56, 189, 248, 0.15)"

  // ── Auth helper ───────────────────────────────────────────────────────────────

  const clearAuthAndRedirect = useCallback(() => {
    if (typeof window !== "undefined") {
      localStorage.removeItem("token")
      localStorage.removeItem("user")
    }
    setUser(null as unknown as CurrentUser | null)
    router.push("/login")
  }, [router, setUser])

  // ── Data fetching ─────────────────────────────────────────────────────────────

  const fetchFileData = useCallback(async () => {
    try {
      const res = await API.get<FileType>(`/files/${fileId}`)
      setFile(res.data)
      return res.data
    } catch (err: any) {
      if (err?.response?.status === 401) clearAuthAndRedirect()
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
      // Non-fatal
    }
  }, [fileId])

  // ── Polling for processing status ─────────────────────────────────────────────

  const startPolling = useCallback(() => {
    if (pollIntervalRef.current) return
    pollIntervalRef.current = setInterval(async () => {
      const updated = await fetchFileData()
      if (updated && (updated.processing_status === "completed" || updated.processing_status === "failed")) {
        clearInterval(pollIntervalRef.current!)
        pollIntervalRef.current = null
        if (updated.processing_status === "completed") {
          await fetchHistory()
        }
      }
    }, 3000)
  }, [fetchFileData, fetchHistory])

  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
    }
  }, [])

  // ── Initial load ──────────────────────────────────────────────────────────────

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
        const foundFolder = foldersRes.data.find((f) => f.id === folderId)
        setFolder(foundFolder ?? null)
        const f = fileRes.data
        setFile(f)
        setFiles(filesRes.data)

        if (f.processing_status === "completed") {
          await fetchHistory()
        }

        // Auto-poll if file is still processing
        if (f.processing_status === "pending" || f.processing_status === "processing") {
          startPolling()
        }
      } catch (err: any) {
        if (err?.response?.status === 401) clearAuthAndRedirect()
        else if (err?.response?.status === 403) setError("You are not a member of this classroom")
        else setError("Failed to load. Please try again.")
      } finally {
        setLoading(false)
      }
    }

    load()
  }, [userLoading, user, classroomId, folderId, fileId])

  // Scroll to newest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  // ── Chat ──────────────────────────────────────────────────────────────────────

  const handleAsk = async () => {
    if (!question.trim() || isAsking || !isCompleted) return
    const q = question.trim()
    setQuestion("")
    setChatError(null)
    setIsAsking(true)

    const tempId = Date.now()
    const tempUserMsg: ChatMessage = { id: tempId, role: "user", content: q, timestamp: new Date().toISOString() }
    setMessages((prev) => [...prev, tempUserMsg])

    try {
      const res = await API.post<{ answer: string; message_id: number }>(
        `/chat/files/${fileId}/ask`,
        { question: q }
      )
      setMessages((prev) => [
        ...prev,
        { id: res.data.message_id, role: "assistant", content: res.data.answer, timestamp: new Date().toISOString() },
      ])
    } catch (err: any) {
      const detail = err?.response?.data?.detail
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
      const url = res.data?.download_url
      if (url && typeof window !== "undefined") window.open(url, "_blank")
      else setActionError("Failed to get download link.")
    } catch (err: any) {
      setActionError(normalizeErrorDetail(err?.response?.data?.detail, "Failed to download file."))
    } finally {
      setIsDownloading(false)
    }
  }

  const handleManualRefresh = async () => {
    const updated = await fetchFileData()
    if (updated?.processing_status === "completed") {
      await fetchHistory()
    }
  }

  const handleReprocess = async () => {
    try {
      await API.post(`/files/${fileId}/reprocess`)
      setFile((prev) => prev ? { ...prev, processing_status: "pending", description: null } : prev)
      setMessages([])
      startPolling()
    } catch (err: any) {
      setActionError(normalizeErrorDetail(err?.response?.data?.detail, "Failed to start reprocessing."))
    }
  }

  // ── Derived ───────────────────────────────────────────────────────────────────

  const isOwner = user && classroom && user.id === classroom.owner_id
  const summary = file?.description ?? null
  const status = file?.processing_status ?? "pending"
  const isCompleted = status === "completed"
  const isFailed = status === "failed"
  const isInProgress = status === "pending" || status === "processing"
  const canChat = isCompleted

  // ── Status badge ──────────────────────────────────────────────────────────────

  const StatusBadge = () => {
    if (isCompleted) return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 px-3 py-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">
        <CheckCircle2 className="h-3.5 w-3.5" /> Ready
      </span>
    )
    if (isFailed) return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-destructive/10 border border-destructive/30 px-3 py-1 text-xs font-medium text-destructive">
        <AlertCircle className="h-3.5 w-3.5" /> Failed
      </span>
    )
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/10 border border-amber-500/30 px-3 py-1 text-xs font-medium text-amber-600 dark:text-amber-400">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        {status === "processing" ? "Processing…" : "Queued…"}
      </span>
    )
  }

  // ── Loading / error ───────────────────────────────────────────────────────────

  if (loading || userLoading) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <LoadingOverlay isLoading={true} progress={0} message="Loading file…" size="xl" fullScreen={true} />
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

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div className="relative min-h-screen w-full overflow-x-hidden bg-background">
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

        <main className={`flex-1 flex flex-col h-[calc(100vh-4rem)] transition-all duration-300 ${sidebarCollapsed ? "ml-0" : "ml-[280px]"}`}>

          {/* Background */}
          <div className="absolute inset-0 top-16 opacity-60 pointer-events-none z-0">
            <Squares speed={0.5} squareSize={40} direction="diagonal" borderColor={borderColor} hoverFillColor={hoverFillColor} />
          </div>

          <div className="relative z-10 flex flex-col h-full px-6 pt-6 pb-4 gap-4">

            {/* File header row */}
            <div className="flex items-center justify-between gap-3 shrink-0">
              <div className="flex items-center gap-3 min-w-0">
                <FileText className="h-5 w-5 text-primary shrink-0" />
                <h2 className="truncate text-xl font-semibold text-foreground">{file.filename}</h2>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <StatusBadge />
                {isFailed && (
                  <button onClick={handleReprocess}
                    className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 border border-primary/30 px-3 py-1 text-xs font-medium text-primary hover:bg-primary/20 cursor-pointer">
                    <RefreshCw className="h-3 w-3" /> Retry
                  </button>
                )}
                {isCompleted && (
                  <button onClick={handleManualRefresh} title="Refresh"
                    className="p-1.5 rounded-md border border-border hover:bg-card/70 text-muted-foreground cursor-pointer">
                    <RefreshCw className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>

            {/* Action error */}
            {actionError && (
              <div className="shrink-0 rounded-md border border-destructive/40 bg-destructive/5 px-4 py-2 text-sm text-destructive">
                {actionError}
              </div>
            )}

            {/* Summary card */}
            <div className="shrink-0 rounded-xl border border-border bg-card/70 backdrop-blur-sm px-5 py-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                Document Summary
              </p>
              {summary ? (
                <p className="text-sm text-foreground leading-relaxed">{summary}</p>
              ) : isCompleted ? (
                <p className="text-sm text-muted-foreground italic">No summary available for this document.</p>
              ) : isFailed ? (
                <p className="text-sm text-destructive italic">Processing failed. Try re-uploading the file.</p>
              ) : (
                <div className="flex items-center gap-2 text-sm text-muted-foreground italic">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Generating summary… this may take a minute for large files.
                </div>
              )}
            </div>

            {/* ── Chat section ── */}
            <div className="flex-1 flex flex-col min-h-0 rounded-xl border border-border bg-card/50 backdrop-blur-sm overflow-hidden">

              {/* Messages scroll area */}
              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {messages.length === 0 && (
                  <div className="flex flex-col items-center justify-center h-full text-center gap-2 py-8">
                    {canChat ? (
                      <>
                        <CheckCircle2 className="h-6 w-6 text-emerald-500" />
                        <p className="text-sm font-medium text-foreground">Ready to answer questions</p>
                        <p className="text-xs text-muted-foreground">Ask anything about this document below.</p>
                      </>
                    ) : isFailed ? (
                      <>
                        <AlertCircle className="h-6 w-6 text-destructive" />
                        <p className="text-sm text-destructive">Processing failed.</p>
                        <button onClick={handleReprocess}
                          className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 cursor-pointer">
                          <RefreshCw className="h-3.5 w-3.5" /> Retry
                        </button>
                      </>
                    ) : (
                      <>
                        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                        <p className="text-sm text-muted-foreground">
                          Processing document… Q&amp;A will be available shortly.
                        </p>
                        <p className="text-xs text-muted-foreground/60">
                          Large files (PDF, PPTX) may take 2–5 minutes.
                        </p>
                      </>
                    )}
                  </div>
                )}

                {messages.map((msg) => (
                  <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "bg-primary text-primary-foreground rounded-br-sm"
                        : "border border-border bg-card text-foreground rounded-bl-sm"
                    }`}>
                      <p className="whitespace-pre-wrap">{msg.content}</p>
                    </div>
                  </div>
                ))}

                {isAsking && (
                  <div className="flex justify-start">
                    <div className="rounded-2xl rounded-bl-sm border border-border bg-card px-4 py-3 text-sm text-muted-foreground flex items-center gap-2">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" /> Thinking…
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>

              {/* Chat error */}
              {chatError && (
                <p className="px-4 pb-1 text-xs text-destructive shrink-0">{chatError}</p>
              )}

              {/* Input area — always visible */}
              <div className="shrink-0 border-t border-border bg-card/80 p-3">
                <div className="flex items-end gap-2">
                  <textarea
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={handleKeyDown}
                    disabled={isAsking || !canChat}
                    placeholder={
                      isFailed
                        ? "Processing failed — click Retry above"
                        : isInProgress
                        ? "Processing document… check back in a moment"
                        : "Ask a question about this document… (Enter to send, Shift+Enter for new line)"
                    }
                    rows={2}
                    className="flex-1 resize-none rounded-xl border border-border bg-background/60 px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground/70 focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-40 disabled:cursor-not-allowed"
                  />
                  <button
                    type="button"
                    onClick={handleAsk}
                    disabled={!question.trim() || isAsking || !canChat}
                    className="shrink-0 flex items-center justify-center rounded-xl bg-primary w-11 h-11 text-primary-foreground hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
                  >
                    {isAsking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  </button>
                </div>
                <p className="mt-1.5 text-[11px] text-muted-foreground/60 px-1">
                  {canChat ? "Enter to send · Shift+Enter for new line" : isInProgress ? "Processing in background…" : ""}
                </p>
              </div>
            </div>

          </div>
        </main>
      </div>

      {/* Floating download button */}
      <button type="button" onClick={handleDownload} disabled={isDownloading}
        className="fixed bottom-6 right-6 z-40 inline-flex items-center gap-2 rounded-full border border-border/60 bg-primary text-primary-foreground px-5 py-3 shadow-xl shadow-primary/30 hover:bg-primary/90 disabled:opacity-60 cursor-pointer">
        <Download className="h-5 w-5" />
        <span className="text-sm font-medium">{isDownloading ? "Preparing…" : "Download"}</span>
      </button>
    </div>
  )
}
