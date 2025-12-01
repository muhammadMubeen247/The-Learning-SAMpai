"use client"

import { useState, useEffect, useRef } from "react"
import { useParams, useRouter } from "next/navigation"
import dynamic from "next/dynamic"
import { Send, Loader2 } from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"
import API from "@/api/axios"
import { useCurrentUser, type CurrentUser } from "@/hooks/use-current-user"
import { normalizeErrorDetail } from "@/lib/error-utils"
import { useTheme } from "@/hooks/use-theme"
import ClassroomSidebar from "@/components/classroom/sidebar"
import ClassroomHeader from "@/components/classroom/header"
import AnimatedList from "@/components/backgrounds/animated-list"
import { cn } from "@/lib/utils"
import { LoadingOverlay } from "@/components/ui/liquid-orb-loader"

const Squares = dynamic(() => import("@/components/backgrounds/squares"), { ssr: false })
const Plasma = dynamic(() => import("@/components/backgrounds/plasma"), { ssr: false })

type Classroom = {
  id: number
  name: string
  description: string | null
  code: string
  owner_id: number
  members: {
    id: number
    username: string
    email: string
  }[]
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
}

type ChatMessage = {
  id: number
  topic_id: number
  user_id: number
  role: "user" | "assistant" | "system"
  content: string
  timestamp: string
  metadata: string | null
}

export default function TopicChatPage() {
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
  const [files, setFiles] = useState<FileType[]>([])
  const [topic, setTopic] = useState<Topic | null>(null)
  const [topics, setTopics] = useState<Topic[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [question, setQuestion] = useState("")
  const [isAsking, setIsAsking] = useState(false)
  const [streamingMessage, setStreamingMessage] = useState<string | null>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)

  // Theme-appropriate colors
  const borderColor = theme === "dark" ? "rgba(147, 197, 253, 0.3)" : "rgba(56, 189, 248, 0.4)"
  const hoverFillColor = theme === "dark" ? "rgba(147, 197, 253, 0.1)" : "rgba(56, 189, 248, 0.15)"
  const plasmaColor = theme === "dark" ? "#60a5fa" : "#3b82f6"

  const fetchClassroom = async () => {
    try {
      const res = await API.get<Classroom>(`/classrooms/${classroomId}`)
      setClassroom(res.data)
    } catch (err: any) {
      if (err?.response?.status === 401) {
        if (typeof window !== "undefined") {
          localStorage.removeItem("token")
          localStorage.removeItem("user")
        }
        setUser(null as unknown as CurrentUser | null)
        router.push("/login")
      } else if (err?.response?.status === 403) {
        setError("You are not a member of this classroom")
      } else if (err?.response?.status === 404) {
        setError("Classroom not found")
      } else {
        setError("Failed to load classroom. Please try again.")
      }
    }
  }

  const fetchFolder = async () => {
    try {
      const res = await API.get<Folder[]>(`/folders/classroom/${classroomId}`)
      const foundFolder = res.data.find((f) => f.id === folderId)
      if (foundFolder) {
        setFolder(foundFolder)
      } else {
        setError("Folder not found")
      }
    } catch (err: any) {
      if (err?.response?.status === 401) {
        if (typeof window !== "undefined") {
          localStorage.removeItem("token")
          localStorage.removeItem("user")
        }
        setUser(null as unknown as CurrentUser | null)
        router.push("/login")
      } else {
        setError("Failed to load folder")
      }
    }
  }

  const fetchFile = async () => {
    try {
      const res = await API.get<FileType & { topics: Topic[] }>(`/files/${fileId}`)
      setFile(res.data)
      setTopics(res.data.topics || [])
      const foundTopic = res.data.topics?.find((t) => t.id === topicId)
      if (foundTopic) {
        setTopic(foundTopic)
      } else {
        setError("Topic not found")
      }
    } catch (err: any) {
      if (err?.response?.status === 401) {
        if (typeof window !== "undefined") {
          localStorage.removeItem("token")
          localStorage.removeItem("user")
        }
        setUser(null as unknown as CurrentUser | null)
        router.push("/login")
      } else if (err?.response?.status === 403) {
        setError("You are not a member of this classroom")
      } else if (err?.response?.status === 404) {
        setError("File not found")
      } else {
        setError("Failed to load file. Please try again.")
      }
    }
  }

  const fetchFiles = async () => {
    try {
      const res = await API.get<FileType[]>(`/files/folder/${folderId}`)
      setFiles(res.data)
    } catch (err: any) {
      if (err?.response?.status === 401) {
        if (typeof window !== "undefined") {
          localStorage.removeItem("token")
          localStorage.removeItem("user")
        }
        setUser(null as unknown as CurrentUser | null)
        router.push("/login")
      } else {
        console.error("Failed to load files:", err)
      }
    }
  }

  const fetchChatHistory = async () => {
    try {
      const res = await API.get<{ messages: ChatMessage[]; total: number; offset: number; limit: number }>(
        `/chat/topics/${topicId}/history`
      )
      setMessages(res.data.messages || [])
    } catch (err: any) {
      if (err?.response?.status === 401) {
        if (typeof window !== "undefined") {
          localStorage.removeItem("token")
          localStorage.removeItem("user")
        }
        setUser(null as unknown as CurrentUser | null)
        router.push("/login")
      } else {
        console.error("Failed to load chat history:", err)
      }
    }
  }

  const streamText = (text: string, onUpdate: (text: string) => void, onComplete: () => void) => {
    let index = 0
    const chars = text.split("")
    const streamInterval = setInterval(() => {
      if (index < chars.length) {
        onUpdate(chars.slice(0, index + 1).join(""))
        index++
      } else {
        clearInterval(streamInterval)
        onComplete()
      }
    }, 15) // Fast character-by-character streaming - 15ms per character
    return () => clearInterval(streamInterval)
  }

  const handleAskQuestion = async (e: React.FormEvent) => {
    e.preventDefault()
    const questionText = question.trim()
    if (!questionText || isAsking) return

    setIsAsking(true)
    setQuestion("")
    
    // Add user message immediately
    const userMessage: ChatMessage = {
      id: Date.now(), // Temporary ID
      topic_id: topicId,
      user_id: user?.id ?? 0,
      role: "user",
      content: questionText,
      timestamp: new Date().toISOString(),
      metadata: null,
    }
    setMessages((prev) => [...prev, userMessage])

    try {
      const res = await API.post<{
        answer: string
        sources: any[]
        confidence: string
        chunks_used: number
        message_id: number
      }>(`/chat/topics/${topicId}/ask`, {
        question: questionText,
        file_id: fileId,
      })

      // Stream the answer
      streamText(
        res.data.answer,
        (streamedText) => {
          setStreamingMessage(streamedText)
        },
        () => {
          // After streaming completes, add to messages
          const assistantMessage: ChatMessage = {
            id: res.data.message_id,
            topic_id: topicId,
            user_id: user?.id ?? 0,
            role: "assistant",
            content: res.data.answer,
            timestamp: new Date().toISOString(),
            metadata: JSON.stringify({
              confidence: res.data.confidence,
              chunks_used: res.data.chunks_used,
            }),
          }
          setMessages((prev) => [...prev, assistantMessage])
          setStreamingMessage(null)
          setIsAsking(false)
        }
      )
    } catch (err: any) {
      setIsAsking(false)
      if (err?.response?.status === 401) {
        if (typeof window !== "undefined") {
          localStorage.removeItem("token")
          localStorage.removeItem("user")
        }
        router.push("/login")
      } else {
        const detail = err?.response?.data?.detail
        setError(normalizeErrorDetail(detail, "Failed to ask question. Please try again."))
        // Remove the user message on error
        setMessages((prev) => prev.filter((m) => m.id !== userMessage.id))
      }
    } finally {
      setIsAsking(false)
    }
  }

  useEffect(() => {
    if (userLoading) return
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null
    if (!user || !token) {
      router.push("/login")
      return
    }
    if (classroomId && !isNaN(classroomId) && folderId && !isNaN(folderId) && fileId && !isNaN(fileId) && topicId && !isNaN(topicId)) {
      Promise.all([fetchClassroom(), fetchFolder(), fetchFile(), fetchFiles(), fetchChatHistory()]).finally(() => {
        setLoading(false)
      })
    }
  }, [userLoading, user, classroomId, folderId, fileId, topicId, router])

  // Scroll to bottom when messages change
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: "smooth" })
    }
  }, [messages, streamingMessage])

  const isOwner = user && classroom && user.id === classroom.owner_id
  const topicNames = topics.map((t) => t.topic_name)

  if (loading || userLoading) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <LoadingOverlay 
          isLoading={true} 
          progress={0}
          message="Loading chat..."
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
          files={files}
          topics={topics}
          currentFileId={fileId}
          currentTopicId={topicId}
          onFolderClick={() => router.push(`/classroom/${classroomId}/folder/${folderId}`)}
          onFileSelect={(fileId) => router.push(`/classroom/${classroomId}/folder/${folderId}/file/${fileId}`)}
          onTopicSelect={(selectedTopicId) => router.push(`/classroom/${classroomId}/folder/${folderId}/file/${fileId}/topic/${selectedTopicId}`)}
          onHomeClick={() => {
            if (isOwner) {
              router.push("/created")
            } else {
              router.push("/joined")
            }
          }}
        />

        <main
          className={`flex-1 flex flex-col h-[calc(100vh-4rem)] transition-all duration-300 ${
            sidebarCollapsed ? "ml-0" : "ml-[280px]"
          }`}
        >
          {/* Main Content Area with Plasma Background */}
          <div className="relative flex-1 overflow-hidden h-full">
            <div 
              className="fixed opacity-60 pointer-events-none z-0"
              style={{ 
                left: sidebarCollapsed ? '0' : '280px',
                top: '64px',
                right: '0',
                bottom: '0',
                width: sidebarCollapsed ? '100%' : 'calc(100% - 280px)',
                height: 'calc(100vh - 64px)'
              }}
            >
              <Plasma
                color={plasmaColor}
                speed={0.6}
                direction="forward"
                scale={1.08}
                opacity={0.6}
                mouseInteractive={false}
              />
            </div>

            <div className="relative z-10 h-full flex flex-col">
              {/* Chat Messages */}
              <div
                ref={messagesContainerRef}
                className="flex-1 overflow-y-auto px-8 py-8 pb-24 space-y-6"
                style={{ scrollBehavior: "smooth" }}
              >
                {/* Topic Introduction - AI Response Style */}
                {topic.introduction && (
                  <motion.div
                    initial={{ opacity: 0, x: 100, scale: 0.95 }}
                    animate={{ opacity: 1, x: 0, scale: 1 }}
                    transition={{ duration: 0.4, ease: "easeOut" }}
                    className="flex justify-end"
                  >
                    <div className="max-w-2xl rounded-2xl bg-card/80 backdrop-blur-sm border border-border p-6 shadow-lg">
                      <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">
                        {topic.introduction}
                      </p>
                    </div>
                  </motion.div>
                )}

                {/* Chat Messages */}
                <AnimatePresence mode="popLayout">
                  {messages.map((message, index) => (
                    <motion.div
                      key={message.id}
                      layout
                      initial={{ opacity: 0, y: 30, scale: 0.9 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: -20, scale: 0.9 }}
                      transition={{
                        type: "spring",
                        stiffness: 400,
                        damping: 25,
                        duration: 0.4,
                      }}
                      className={cn(
                        "flex",
                        message.role === "user" ? "justify-start" : "justify-end"
                      )}
                    >
                      <motion.div
                        initial={{ scale: 0.8, y: 20 }}
                        animate={{ scale: 1, y: 0 }}
                        transition={{
                          type: "spring",
                          stiffness: 500,
                          damping: 30,
                          delay: 0.1,
                        }}
                        className={cn(
                          "max-w-2xl rounded-2xl p-6 shadow-lg backdrop-blur-sm",
                          message.role === "user"
                            ? "bg-chart-1/20 border border-chart-1/30"
                            : "bg-card/80 border border-border"
                        )}
                      >
                        <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">
                          {message.content}
                        </p>
                      </motion.div>
                    </motion.div>
                  ))}
                </AnimatePresence>

                {/* AI Thinking Animation - Shows when waiting for response */}
                {isAsking && !streamingMessage && (
                  <motion.div
                    initial={{ opacity: 0, x: 100, scale: 0.9 }}
                    animate={{ opacity: 1, x: 0, scale: 1 }}
                    transition={{
                      type: "spring",
                      stiffness: 400,
                      damping: 25,
                      duration: 0.4,
                    }}
                    className="flex justify-end"
                  >
                    <motion.div
                      initial={{ scale: 0.8 }}
                      animate={{ 
                        scale: 1,
                        y: [0, -4, 0]
                      }}
                      transition={{
                        scale: {
                          type: "spring",
                          stiffness: 500,
                          damping: 30,
                        },
                        y: {
                          duration: 1.5,
                          repeat: Infinity,
                          ease: "easeInOut"
                        }
                      }}
                      className="max-w-2xl rounded-2xl bg-card/80 backdrop-blur-sm border border-border p-6 shadow-lg"
                    >
                      <div className="flex items-center gap-1.5">
                        <motion.span
                          animate={{ 
                            opacity: [0.3, 1, 0.3],
                            y: [0, -3, 0]
                          }}
                          transition={{
                            opacity: {
                              duration: 1.4,
                              repeat: Infinity,
                              ease: "easeInOut",
                            },
                            y: {
                              duration: 1.4,
                              repeat: Infinity,
                              ease: "easeInOut",
                            }
                          }}
                          className="w-2 h-2 rounded-full bg-foreground/60"
                        />
                        <motion.span
                          animate={{ 
                            opacity: [0.3, 1, 0.3],
                            y: [0, -3, 0]
                          }}
                          transition={{
                            opacity: {
                              duration: 1.4,
                              repeat: Infinity,
                              ease: "easeInOut",
                              delay: 0.2,
                            },
                            y: {
                              duration: 1.4,
                              repeat: Infinity,
                              ease: "easeInOut",
                              delay: 0.2,
                            }
                          }}
                          className="w-2 h-2 rounded-full bg-foreground/60"
                        />
                        <motion.span
                          animate={{ 
                            opacity: [0.3, 1, 0.3],
                            y: [0, -3, 0]
                          }}
                          transition={{
                            opacity: {
                              duration: 1.4,
                              repeat: Infinity,
                              ease: "easeInOut",
                              delay: 0.4,
                            },
                            y: {
                              duration: 1.4,
                              repeat: Infinity,
                              ease: "easeInOut",
                              delay: 0.4,
                            }
                          }}
                          className="w-2 h-2 rounded-full bg-foreground/60"
                        />
                      </div>
                    </motion.div>
                  </motion.div>
                )}

                {/* Streaming Message */}
                {streamingMessage && (
                  <motion.div
                    initial={{ opacity: 0, x: 100, scale: 0.9 }}
                    animate={{ opacity: 1, x: 0, scale: 1 }}
                    transition={{
                      type: "spring",
                      stiffness: 400,
                      damping: 25,
                      duration: 0.4,
                    }}
                    className="flex justify-end"
                  >
                    <motion.div
                      initial={{ scale: 0.8 }}
                      animate={{ scale: 1 }}
                      transition={{
                        type: "spring",
                        stiffness: 500,
                        damping: 30,
                      }}
                      className="max-w-2xl rounded-2xl bg-card/80 backdrop-blur-sm border border-border p-6 shadow-lg"
                    >
                      <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">
                        {streamingMessage}
                        <motion.span
                          animate={{ opacity: [1, 0.3, 1] }}
                          transition={{ duration: 1, repeat: Infinity }}
                          className="inline-block w-2 h-4 bg-foreground/60 ml-1"
                        />
                      </p>
                    </motion.div>
                  </motion.div>
                )}

                <div ref={chatEndRef} />
              </div>

              {/* Chat Input - Fixed at bottom */}
              <div 
                className="fixed bottom-0 border-t border-border bg-background/80 backdrop-blur-xl p-6 z-20"
                style={{ 
                  left: sidebarCollapsed ? '0' : '280px', 
                  right: '0'
                }}
              >
                <form onSubmit={handleAskQuestion} className="max-w-4xl mx-auto">
                  <div className="flex items-center gap-3">
                    <div className="flex-1 relative">
                      <textarea
                        value={question}
                        onChange={(e) => setQuestion(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault()
                            handleAskQuestion(e)
                          }
                        }}
                        placeholder="Ask a question about this topic..."
                        rows={1}
                        className="w-full rounded-xl border border-border bg-card/50 backdrop-blur-sm px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground resize-none focus:outline-none focus:ring-2 focus:ring-chart-1/50 transition-all"
                        style={{
                          minHeight: "48px",
                          maxHeight: "120px",
                        }}
                        disabled={isAsking}
                      />
                    </div>
                    <motion.button
                      type="submit"
                      disabled={!question.trim() || isAsking}
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                      className="rounded-xl bg-chart-1 hover:bg-chart-1/90 text-primary-foreground h-12 w-12 flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed transition-all cursor-pointer shrink-0"
                    >
                      <Send className="size-5" />
                    </motion.button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}


