"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { useParams, useRouter } from "next/navigation"
import dynamic from "next/dynamic"
import API from "@/api/axios"
import { useCurrentUser, type CurrentUser } from "@/hooks/use-current-user"
import { useTheme } from "@/hooks/use-theme"
import ClassroomSidebar from "@/components/classroom/sidebar"
import ClassroomHeader from "@/components/classroom/header"
import { LoadingOverlay } from "@/components/ui/liquid-orb-loader"
import { Send } from "lucide-react"

const Squares = dynamic(() => import("@/components/backgrounds/squares"), { ssr: false })

type Classroom = {
  id: number
  name: string
  description: string | null
  code: string
  owner_id: number
  members: { id: number; username: string; email: string }[]
}

type Folder = {
  id: number
  name: string
  classroom_id: number
}

type Topic = {
  id: number
  topic_name: string
  introduction: string | null
  order: number
  file_id: number
}

type FileType = {
  id: number
  filename: string
  file_url: string
  file_key: string
  file_type: string | null
  file_size: number | null
  processing_status: string
  folder_id: number
  uploaded_at: string
  processed_at: string | null
  topics: Topic[]
}

type ChatMessage = {
  id: number
  topic_id: number
  user_id: number
  role: "user" | "assistant"
  content: string
  timestamp: string
  metadata?: string | null
}

type SourceInfo = {
  file_id: number
  page_number: number | null
  slide_number: number | null
  content_preview: string
}

type QuestionResponse = {
  answer: string
  sources: SourceInfo[]
  confidence: string
  chunks_used: number
  message_id: number
}

export default function TopicPage() {
  const params = useParams()
  const router = useRouter()
  const classroomId = parseInt(params.id as string, 10)
  const folderId = parseInt(params.folderId as string, 10)
  const fileId = parseInt(params.fileId as string, 10)
  const topicId = parseInt(params.topicId as string, 10)

  const { user, loading: userLoading, setUser } = useCurrentUser()
  const { theme } = useTheme()

  const [classroom, setClassroom] = useState<Classroom | null>(null)
  const [folder, setFolder] = useState<Folder | null>(null)
  const [file, setFile] = useState<FileType | null>(null)
  const [topic, setTopic] = useState<Topic | null>(null)
  const [topics, setTopics] = useState<Topic[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  const [question, setQuestion] = useState("")
  const [asking, setAsking] = useState(false)
  const [askError, setAskError] = useState<string | null>(null)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const borderColor = theme === "dark" ? "rgba(147, 197, 253, 0.3)" : "rgba(56, 189, 248, 0.4)"
  const hoverFillColor = theme === "dark" ? "rgba(147, 197, 253, 0.1)" : "rgba(56, 189, 248, 0.15)"

  const handleAuthError = useCallback(() => {
    if (typeof window !== "undefined") {
      localStorage.removeItem("token")
      localStorage.removeItem("user")
    }
    setUser(null as unknown as CurrentUser | null)
    router.push("/login")
  }, [router, setUser])

  const fetchClassroom = useCallback(async () => {
    try {
      const res = await API.get<Classroom>(`/classrooms/${classroomId}`)
      setClassroom(res.data)
    } catch (err: any) {
      if (err?.response?.status === 401) handleAuthError()
      else if (err?.response?.status === 403) setError("You are not a member of this classroom")
      else if (err?.response?.status === 404) setError("Classroom not found")
      else setError("Failed to load classroom")
    }
  }, [classroomId, handleAuthError])

  const fetchFolder = useCallback(async () => {
    try {
      const res = await API.get<Folder[]>(`/folders/classroom/${classroomId}`)
      const found = res.data.find((f) => f.id === folderId)
      if (found) setFolder(found)
      else setError("Folder not found")
    } catch (err: any) {
      if (err?.response?.status === 401) handleAuthError()
      else setError("Failed to load folder")
    }
  }, [classroomId, folderId, handleAuthError])

  const fetchFile = useCallback(async () => {
    try {
      const res = await API.get<FileType>(`/files/${fileId}`)
      setFile(res.data)
      const allTopics = res.data.topics || []
      setTopics(allTopics)
      const found = allTopics.find((t) => t.id === topicId)
      if (found) setTopic(found)
      else setError("Topic not found")
    } catch (err: any) {
      if (err?.response?.status === 401) handleAuthError()
      else if (err?.response?.status === 404) setError("File not found")
      else setError("Failed to load file")
    }
  }, [fileId, topicId, handleAuthError])

  const fetchHistory = useCallback(async () => {
    try {
      const res = await API.get<{ messages: ChatMessage[]; total: number }>(
        `/chat/topics/${topicId}/history?limit=100&offset=0`
      )
      setMessages(res.data.messages)
    } catch (err: any) {
      if (err?.response?.status === 401) handleAuthError()
      // history failure is non-fatal; leave messages empty
    }
  }, [topicId, handleAuthError])

  useEffect(() => {
    if (userLoading) return
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null
    if (!user || !token) {
      router.push("/login")
      return
    }
    if (
      !isNaN(classroomId) && !isNaN(folderId) &&
      !isNaN(fileId) && !isNaN(topicId)
    ) {
      Promise.all([fetchClassroom(), fetchFolder(), fetchFile(), fetchHistory()]).finally(() => {
        setLoading(false)
      })
    }
  }, [userLoading, user, classroomId, folderId, fileId, topicId, router,
      fetchClassroom, fetchFolder, fetchFile, fetchHistory])

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, asking])

  const handleAsk = async () => {
    const trimmed = question.trim()
    if (!trimmed || asking) return
    setAskError(null)
    setAsking(true)

    // Optimistically add user message
    const optimisticUser: ChatMessage = {
      id: Date.now(),
      topic_id: topicId,
      user_id: user!.id,
      role: "user",
      content: trimmed,
      timestamp: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, optimisticUser])
    setQuestion("")
    if (textareaRef.current) textareaRef.current.style.height = "auto"

    try {
      const res = await API.post<QuestionResponse>(`/chat/topics/${topicId}/ask`, {
        question: trimmed,
        file_id: fileId,
      })
      const assistantMsg: ChatMessage = {
        id: res.data.message_id,
        topic_id: topicId,
        user_id: user!.id,
        role: "assistant",
        content: res.data.answer,
        timestamp: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, assistantMsg])
    } catch (err: any) {
      if (err?.response?.status === 401) {
        handleAuthError()
      } else if (err?.response?.status === 400) {
        setAskError(err?.response?.data?.detail || "File is still being processed.")
        // Remove optimistic message
        setMessages((prev) => prev.filter((m) => m.id !== optimisticUser.id))
      } else {
        setAskError("Failed to get a response. Please try again.")
        setMessages((prev) => prev.filter((m) => m.id !== optimisticUser.id))
      }
    } finally {
      setAsking(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      void handleAsk()
    }
  }

  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setQuestion(e.target.value)
    // Auto-resize
    e.target.style.height = "auto"
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px"
  }

  const isOwner = user && classroom && user.id === classroom.owner_id

  if (loading || userLoading) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <LoadingOverlay
          isLoading={true}
          progress={0}
          message="Loading topic..."
          size="xl"
          fullScreen={true}
        />
      </div>
    )
  }

  if (error || !classroom || !folder || !file || !topic) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-destructive">{error || "Topic not found"}</p>
          <button
            onClick={() => router.push(`/classroom/${classroomId}/folder/${folderId}/file/${fileId}`)}
            className="px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer"
          >
            Back to File
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="relative min-h-screen w-full overflow-x-hidden bg-background">
      <ClassroomHeader
        classroomName={classroom.name}
        folderName={folder.name}
        fileName={file.filename}
        topicName={topic.topic_name}
        classroomId={classroomId}
        folderId={folderId}
        fileId={fileId}
        username={user?.username ?? ""}
        onMenuClick={() => setSidebarCollapsed(!sidebarCollapsed)}
        onLogout={() => {
          if (typeof window !== "undefined") {
            localStorage.removeItem("token")
            localStorage.removeItem("user")
          }
          setUser(null as unknown as CurrentUser | null)
          router.push("/login")
        }}
      />

      <div className="flex pt-16">
        <ClassroomSidebar
          collapsed={sidebarCollapsed}
          currentClassroomId={classroomId}
          mode="topic"
          folderId={folderId}
          topics={topics}
          currentTopicId={topicId}
          onFolderClick={() => router.push(`/classroom/${classroomId}/folder/${folderId}`)}
          onTopicSelect={(id) =>
            router.push(`/classroom/${classroomId}/folder/${folderId}/file/${fileId}/topic/${id}`)
          }
          onHomeClick={() => {
            if (isOwner) router.push("/created")
            else router.push("/joined")
          }}
        />

        <main
          className={`flex-1 flex flex-col h-[calc(100vh-4rem)] transition-all duration-300 ${
            sidebarCollapsed ? "ml-0" : "ml-[280px]"
          }`}
        >
          <div className="relative flex-1 overflow-hidden flex flex-col">
            {/* Background */}
            <div className="absolute inset-0 opacity-60 pointer-events-none z-0">
              <Squares
                speed={0.5}
                squareSize={40}
                direction="diagonal"
                borderColor={borderColor}
                hoverFillColor={hoverFillColor}
              />
            </div>

            {/* Topic header */}
            <div className="relative z-10 px-8 pt-8 pb-4 border-b border-border/50 bg-background/60 backdrop-blur-sm">
              <h2 className="text-xl font-semibold text-foreground truncate">{topic.topic_name}</h2>
              {topic.introduction && (
                <p className="mt-1 text-sm text-muted-foreground line-clamp-2">{topic.introduction}</p>
              )}
            </div>

            {/* Messages */}
            <div className="relative z-10 flex-1 overflow-y-auto px-8 py-6 space-y-4">
              {messages.length === 0 && (
                <div className="flex flex-col items-center justify-center h-full text-center gap-3 opacity-60">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="size-10 text-muted-foreground"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={1.5}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M8.625 9.75a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375m-13.5 3.01c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.184-4.183a1.14 1.14 0 0 1 .778-.332 48.294 48.294 0 0 0 5.83-.498c1.585-.233 2.708-1.626 2.708-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z"
                    />
                  </svg>
                  <p className="text-sm text-muted-foreground">
                    Ask a question about <span className="font-medium text-foreground">{topic.topic_name}</span>
                  </p>
                </div>
              )}

              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
                      msg.role === "user"
                        ? "bg-primary text-primary-foreground rounded-br-sm"
                        : "bg-card border border-border text-foreground rounded-bl-sm"
                    }`}
                  >
                    {msg.content}
                  </div>
                </div>
              ))}

              {/* Thinking indicator */}
              {asking && (
                <div className="flex justify-start">
                  <div className="bg-card border border-border rounded-2xl rounded-bl-sm px-4 py-3 flex items-center gap-1.5">
                    <span className="size-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:-0.3s]" />
                    <span className="size-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:-0.15s]" />
                    <span className="size-1.5 rounded-full bg-muted-foreground animate-bounce" />
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Error banner */}
            {askError && (
              <div className="relative z-10 mx-8 mb-2 rounded-md border border-destructive/40 bg-destructive/5 px-4 py-2 text-sm text-destructive">
                {askError}
              </div>
            )}

            {/* Input */}
            <div className="relative z-10 px-8 pb-6 pt-3 bg-background/60 backdrop-blur-sm border-t border-border/50">
              <div className="flex items-end gap-3 rounded-xl border border-border bg-card/70 px-4 py-3">
                <textarea
                  ref={textareaRef}
                  value={question}
                  onChange={handleTextareaChange}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask a question about this topic…"
                  rows={1}
                  disabled={asking}
                  className="flex-1 resize-none bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none disabled:opacity-50"
                  style={{ maxHeight: "160px" }}
                />
                <button
                  type="button"
                  onClick={() => void handleAsk()}
                  disabled={!question.trim() || asking}
                  className="shrink-0 p-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  aria-label="Send"
                >
                  <Send className="size-4" />
                </button>
              </div>
              <p className="mt-2 text-xs text-muted-foreground text-center">
                Press Enter to send · Shift+Enter for new line
              </p>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
