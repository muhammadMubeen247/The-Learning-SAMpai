"use client"

import { useState, useEffect, useRef } from "react"
import { useParams, useRouter, usePathname } from "next/navigation"
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

export default function ClassroomPage() {
  const params = useParams()
  const router = useRouter()
  const pathname = usePathname()
  const classroomId = parseInt(params.id as string, 10)
  const { user, loading: userLoading, setUser } = useCurrentUser()
  const { theme } = useTheme()

  const [classroom, setClassroom] = useState<Classroom | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  const fetchClassroom = async () => {
    setLoading(true)
    setError(null)
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
    } finally {
      setLoading(false)
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
  const plasmaColor = theme === "dark" ? "#60a5fa" : "#3b82f6"

  if (loading || userLoading) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <p className="text-muted-foreground">Loading classroom...</p>
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
          {/* Folders Section with Squares Background */}
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
              <FoldersSection
                classroomId={classroomId}
                isOwner={isOwner ?? false}
                onFolderCreated={() => {
                  // Refetch folders will be handled by FoldersSection
                }}
              />
            </div>
          </div>

          {/* Announcements Section with Plasma Background */}
          <div className="relative border-t border-border">
            <div className="absolute inset-0 opacity-80 pointer-events-none z-0">
              <Plasma
                key={`plasma-${pathname}`}
                color={plasmaColor}
                speed={0.6}
                direction="forward"
                scale={1.08}
                opacity={0.6}
                mouseInteractive={false}
              />
            </div>
            <div className="relative z-10">
              <AnnouncementsSection isOwner={isOwner ?? false} />
            </div>
          </div>
        </main>

        {/* Floating Classroom Code Display (Owner Only) */}
        {isOwner && <ClassroomCodeDisplay code={classroom.code} isOwner={isOwner ?? false} />}
      </div>
    </div>
  )
}

