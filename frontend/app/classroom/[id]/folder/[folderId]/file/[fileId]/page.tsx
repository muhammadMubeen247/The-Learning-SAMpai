"use client"

import { useState, useEffect } from "react"
import { useParams, useRouter } from "next/navigation"
import dynamic from "next/dynamic"
import API from "@/api/axios"
import { useCurrentUser, type CurrentUser } from "@/hooks/use-current-user"
import { normalizeErrorDetail } from "@/lib/error-utils"
import { useTheme } from "@/hooks/use-theme"
import ClassroomSidebar from "@/components/classroom/sidebar"
import ClassroomHeader from "@/components/classroom/header"
import AnimatedList from "@/components/backgrounds/animated-list"
import { LoadingOverlay } from "@/components/ui/liquid-orb-loader"
import { Download } from "lucide-react"

const Squares = dynamic(() => import("@/components/backgrounds/squares"), { ssr: false })

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
  topics: Topic[]
}

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
  const [topics, setTopics] = useState<Topic[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [isDownloading, setIsDownloading] = useState(false)

  // Theme-appropriate colors for Squares background
  const borderColor = theme === "dark" ? "rgba(147, 197, 253, 0.3)" : "rgba(56, 189, 248, 0.4)"
  const hoverFillColor = theme === "dark" ? "rgba(147, 197, 253, 0.1)" : "rgba(56, 189, 248, 0.15)"

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
      const res = await API.get<FileType>(`/files/${fileId}`)
      setFile(res.data)
      setTopics(res.data.topics || [])
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

  const handleDownload = async () => {
    if (!fileId || isDownloading) return
    setActionError(null)
    setIsDownloading(true)
    try {
      const res = await API.get<{ download_url: string }>(`/files/${fileId}/download`)
      const url = res.data?.download_url
      if (url) {
        if (typeof window !== "undefined") {
          window.open(url, "_blank")
        }
      } else {
        setActionError("Failed to get download link. Please try again.")
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setActionError(normalizeErrorDetail(detail, "Failed to download file."))
    } finally {
      setIsDownloading(false)
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


  useEffect(() => {
    if (userLoading) return
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null
    if (!user || !token) {
      router.push("/login")
      return
    }
    if (classroomId && !isNaN(classroomId) && folderId && !isNaN(folderId) && fileId && !isNaN(fileId)) {
      Promise.all([fetchClassroom(), fetchFolder(), fetchFile(), fetchFiles()]).finally(() => {
        setLoading(false)
      })
    }
  }, [userLoading, user, classroomId, folderId, fileId, router])

  const isOwner = user && classroom && user.id === classroom.owner_id
  const topicNames = topics.map((topic) => topic.topic_name)

  if (loading || userLoading) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <LoadingOverlay 
          isLoading={true} 
          progress={0}
          message="Loading file..."
          size="xl"
          fullScreen={true}
        />
      </div>
    )
  }

  if (error || !classroom || !folder || !file) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-destructive">{error || "File not found"}</p>
          <button
            onClick={() => router.push(`/classroom/${classroomId}/folder/${folderId}`)}
            className="px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer"
          >
            Back to Folder
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
        classroomId={classroomId}
        folderId={folderId}
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
          mode="file"
          folderId={folderId}
          files={files}
          topics={topics}
          currentFileId={fileId}
          onFolderClick={() => router.push(`/classroom/${classroomId}/folder/${folderId}`)}
          onFileSelect={(fileId) => router.push(`/classroom/${classroomId}/folder/${folderId}/file/${fileId}`)}
          onHomeClick={() => {
            // Navigate to joined or created based on ownership
            if (isOwner) {
              router.push("/created")
            } else {
              router.push("/joined")
            }
          }}
        />

        <main
          className={`flex-1 flex flex-col min-h-[calc(100vh-4rem)] transition-all duration-300 ${
            sidebarCollapsed ? "ml-0" : "ml-[280px]"
          }`}
        >
          {/* Optional inline error for actions (download/delete) */}
          {actionError && (
            <div className="mx-8 mt-4 mb-2 rounded-md border border-destructive/40 bg-destructive/5 px-4 py-2 text-sm text-destructive">
              {actionError}
            </div>
          )}

          {/* Main Content Area with Squares Background */}
          <div className="relative flex-1 overflow-hidden">
            <div className="absolute inset-0 opacity-60 pointer-events-none z-0">
              <Squares
                speed={0.5}
                squareSize={40}
                direction="diagonal"
                borderColor={borderColor}
                hoverFillColor={hoverFillColor}
              />
            </div>

            <div className="relative z-10 h-full overflow-y-auto overflow-x-hidden">
              {/* File header */}
              <div className="flex flex-col gap-2 px-8 pt-8">
                <div className="min-w-0">
                  <h2 className="truncate text-2xl font-semibold text-foreground">
                    {file.filename}
                  </h2>
                </div>
              </div>

              {/* Main Content - Topics List */}
              <div className="flex-1 flex flex-col px-8 pb-8 pt-4">
                <div className="mb-6">
                  <h3 className="text-lg font-semibold text-foreground mb-1">Topics</h3>
                  <p className="text-sm text-muted-foreground">
                    Select a topic to view its details
                  </p>
                </div>

                {topics.length === 0 ? (
                  <div className="rounded-lg border border-border bg-card/50 backdrop-blur-sm p-6">
                    <p className="text-sm text-muted-foreground">
                      No topics have been extracted from this file yet.
                    </p>
                  </div>
                ) : (
                  <div className="flex-1 min-h-0">
                    <AnimatedList
                      items={topicNames}
                      onItemSelect={(name, index) => {
                        // Navigate to topic chat page
                        const selectedTopic = topics[index]
                        if (selectedTopic) {
                          router.push(`/classroom/${classroomId}/folder/${folderId}/file/${fileId}/topic/${selectedTopic.id}`)
                        }
                      }}
                      className="w-full h-full"
                      itemClassName="border border-border rounded-lg cursor-pointer"
                      displayScrollbar
                    />
                  </div>
                )}
              </div>
            </div>
          </div>
        </main>
      </div>

      {/* Floating download button - bottom right, fixed */}
      <button
        type="button"
        onClick={handleDownload}
        disabled={isDownloading}
        className="fixed bottom-6 right-6 z-40 inline-flex items-center gap-2 rounded-full border border-border/60 bg-primary text-primary-foreground px-5 py-3 shadow-xl shadow-primary/30 hover:bg-primary/90 disabled:opacity-60 cursor-pointer"
      >
        <Download className="h-5 w-5" />
        <span className="text-sm font-medium">
          {isDownloading ? "Preparing download..." : "Download file"}
        </span>
      </button>
    </div>
  )
}

