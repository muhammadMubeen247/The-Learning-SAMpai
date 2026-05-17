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
import FoldersSection from "@/components/classroom/folders-section"
import AnnouncementsSection from "@/components/classroom/announcements-section"
import ClassroomCodeDisplay from "@/components/classroom/code-display"
import GroupChatsTab from "@/components/classroom/group-chats-tab"
import { LoadingOverlay } from "@/components/ui/liquid-orb-loader"

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

export default function ClassroomPage() {
  const params = useParams()
  const router = useRouter()
  const classroomId = parseInt(params.id as string, 10)
  const { user, loading: userLoading, setUser } = useCurrentUser()
  const { theme } = useTheme()

  const [classroom, setClassroom] = useState<Classroom | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingProgress, setLoadingProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [activeTab, setActiveTab] = useState<"files" | "groups">("files")

  const fetchClassroom = async () => {
    setLoading(true)
    setLoadingProgress(0)
    setError(null)
    
    // Simulate progress for better UX
    const progressInterval = setInterval(() => {
      setLoadingProgress((prev) => {
        if (prev >= 90) return prev
        return prev + Math.random() * 15
      })
    }, 100)
    
    try {
      setLoadingProgress(30)
      const res = await API.get<Classroom>(`/classrooms/${classroomId}`)
      setLoadingProgress(70)
      setClassroom(res.data)
      setLoadingProgress(100)
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
    } finally {
      clearInterval(progressInterval)
      setLoading(false)
      setTimeout(() => setLoadingProgress(0), 500)
    }
  }

  useEffect(() => {
    if (userLoading) return
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null
    if (!user || !token) {
      router.push("/login")
      return
    }
    if (classroomId && !isNaN(classroomId)) {
      void fetchClassroom()
    }
  }, [userLoading, user, classroomId, router])

  const isOwner = user && classroom && user.id === classroom.owner_id

  // Theme-appropriate colors for Squares background
  const borderColor = theme === "dark" ? "rgba(147, 197, 253, 0.3)" : "rgba(56, 189, 248, 0.4)"
  const hoverFillColor = theme === "dark" ? "rgba(147, 197, 253, 0.1)" : "rgba(56, 189, 248, 0.15)"

  if (loading || userLoading) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <LoadingOverlay 
          isLoading={true} 
          progress={loadingProgress}
          message="Loading classroom..."
          size="xl"
          fullScreen={true}
        />
      </div>
    )
  }

  if (error || !classroom) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-destructive">{error || "Classroom not found"}</p>
          <button
            onClick={() => router.push("/dashboard")}
            className="px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="relative min-h-screen w-full overflow-x-hidden bg-background">
      <ClassroomHeader
        classroomName={classroom.name}
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
          {/* Tab bar */}
          <div className="fixed top-16 z-20 flex border-b border-border bg-background/80 backdrop-blur-sm" style={{ width: sidebarCollapsed ? "100%" : "calc(100% - 280px)" }}>
            <button
              onClick={() => setActiveTab("files")}
              className={`px-5 py-2.5 text-sm font-medium transition-colors border-b-2 ${
                activeTab === "files"
                  ? "border-violet-500 text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              Files
            </button>
            <button
              onClick={() => setActiveTab("groups")}
              className={`px-5 py-2.5 text-sm font-medium transition-colors border-b-2 ${
                activeTab === "groups"
                  ? "border-violet-500 text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              Group Chats
            </button>
          </div>

          {/* Tab content */}
          {activeTab === "files" ? (
            <div className="relative flex-1 overflow-hidden">
              {/* Single Squares background for entire files tab */}
              <div className="absolute inset-0 opacity-60 pointer-events-none z-0">
                <Squares
                  speed={0.5}
                  squareSize={40}
                  direction="diagonal"
                  borderColor={borderColor}
                  hoverFillColor={hoverFillColor}
                />
              </div>

              {/* Scrollable page — folders then announcements panel */}
              <div className="relative z-10 h-full overflow-y-auto overflow-x-hidden">
                <FoldersSection
                  classroomId={classroomId}
                  isOwner={isOwner ?? false}
                  onFolderCreated={() => {}}
                />

                {/* Fixed-height announcements panel — sits below folders, scrollable inside */}
                <div className="px-4 sm:px-6 md:px-8 pb-8">
                  <div className="h-[420px]">
                    <AnnouncementsSection
                      classroomId={classroomId}
                      isOwner={isOwner ?? false}
                      currentUserId={user?.id ?? 0}
                    />
                  </div>
                </div>
              </div>
            </div>
          ) : (
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
                <GroupChatsTab classroomId={classroomId} />
              </div>
            </div>
          )}
        </main>

        {/* Floating Classroom Code Display (Owner Only) */}
        {isOwner && <ClassroomCodeDisplay code={classroom.code} isOwner={isOwner ?? false} />}
      </div>
    </div>
  )
}

