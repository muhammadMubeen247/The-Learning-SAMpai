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
import FilesSection from "@/components/classroom/files-section"

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

export default function FolderPage() {
  const params = useParams()
  const router = useRouter()
  const classroomId = parseInt(params.id as string, 10)
  const folderId = parseInt(params.folderId as string, 10)
  const { user, loading: userLoading, setUser } = useCurrentUser()
  const { theme } = useTheme()

  const [classroom, setClassroom] = useState<Classroom | null>(null)
  const [folder, setFolder] = useState<Folder | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  // Theme-appropriate colors for Squares background
  const borderColor = theme === "dark" ? "rgba(255, 255, 255, 0.1)" : "rgba(0, 0, 0, 0.1)"
  const hoverFillColor = theme === "dark" ? "rgba(255, 255, 255, 0.05)" : "rgba(0, 0, 0, 0.05)"

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

  useEffect(() => {
    if (userLoading) return
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null
    if (!user || !token) {
      router.push("/login")
      return
    }
    if (classroomId && !isNaN(classroomId) && folderId && !isNaN(folderId)) {
      Promise.all([fetchClassroom(), fetchFolder()]).finally(() => {
        setLoading(false)
      })
    }
  }, [userLoading, user, classroomId, folderId, router])

  const isOwner = user && classroom && user.id === classroom.owner_id

  if (loading || userLoading) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <p className="text-muted-foreground">Loading folder...</p>
      </div>
    )
  }

  if (error || !classroom || !folder) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-destructive">{error || "Folder not found"}</p>
          <button
            onClick={() => router.push(`/classroom/${classroomId}`)}
            className="px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer"
          >
            Back to Classroom
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
        classroomId={classroomId}
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
          {/* Files Section with Squares Background */}
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
              <FilesSection
                classroomId={classroomId}
                folderId={folderId}
                isOwner={isOwner ?? false}
                onFileUploaded={() => {
                  // Refetch files will be handled by FilesSection
                }}
              />
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}

