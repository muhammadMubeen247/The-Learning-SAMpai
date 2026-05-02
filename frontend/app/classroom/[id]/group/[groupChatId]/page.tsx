"use client"

import { useState, useEffect } from "react"
import { useParams, useRouter } from "next/navigation"
import API from "@/api/axios"
import { useCurrentUser } from "@/hooks/use-current-user"
import { useRealtimeContext } from "@/providers/realtime-provider"
import { GroupChatPanel } from "@/components/group-chat/group-chat-panel"
import ClassroomHeader from "@/components/classroom/header"
import ClassroomSidebar from "@/components/classroom/sidebar"
import { LoadingOverlay } from "@/components/ui/liquid-orb-loader"
import { ArrowLeft } from "lucide-react"

type Member = {
  user_id: number
  role: string
  joined_at: string
  last_read_seq: number
  user: { id: number; username: string }
}

type GroupChat = {
  id: number
  file_id: number
  classroom_id: number
  name: string | null
  is_archived: boolean
  created_at: string
  members: Member[]
}

type FileDetail = {
  id: number
  filename: string
  processing_status: string
}

export default function GroupChatPage() {
  const params = useParams()
  const router = useRouter()
  const classroomId = parseInt(params.id as string, 10)
  const groupChatId = parseInt(params.groupChatId as string, 10)
  const { user, loading: userLoading } = useCurrentUser()
  const { clearUnread } = useRealtimeContext()

  // Clear the unread badge when entering this thread
  useEffect(() => {
    if (groupChatId) clearUnread(groupChatId)
  }, [groupChatId, clearUnread])

  const [thread, setThread] = useState<GroupChat | null>(null)
  const [file, setFile] = useState<FileDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  useEffect(() => {
    if (userLoading) return
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null
    if (!user || !token) {
      router.push("/login")
      return
    }

    const load = async () => {
      try {
        const [gcRes] = await Promise.all([
          API.get<GroupChat>(`/group-chat/threads/${groupChatId}`),
        ])
        const gc = gcRes.data
        setThread(gc)

        const fileRes = await API.get<FileDetail>(`/files/${gc.file_id}`)
        setFile(fileRes.data)
      } catch (err: unknown) {
        const status = (err as { response?: { status?: number } })?.response?.status
        if (status === 403 || status === 404) {
          setError("Group chat not found or you are not a member.")
        } else {
          setError("Failed to load group chat.")
        }
      } finally {
        setLoading(false)
      }
    }

    void load()
  }, [userLoading, user, groupChatId, router])

  if (loading || userLoading) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <LoadingOverlay isLoading message="Loading group chat…" size="xl" fullScreen />
      </div>
    )
  }

  if (error || !thread || !user) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-destructive">{error ?? "Something went wrong."}</p>
          <button
            onClick={() => router.push(`/classroom/${classroomId}`)}
            className="px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70"
          >
            Back to Classroom
          </button>
        </div>
      </div>
    )
  }

  const displayName = thread.name ?? (file ? `${file.filename} — group` : "Group Chat")

  return (
    <div className="relative min-h-screen w-full bg-background overflow-x-hidden">
      <ClassroomHeader
        classroomName={displayName}
        username={user.username}
        onMenuClick={() => setSidebarCollapsed(!sidebarCollapsed)}
        onLogout={() => {
          if (typeof window !== "undefined") {
            localStorage.removeItem("token")
            localStorage.removeItem("user")
          }
          router.push("/login")
        }}
      />

      <div className="flex pt-16 h-screen">
        <ClassroomSidebar
          collapsed={sidebarCollapsed}
          currentClassroomId={classroomId}
          onHomeClick={() => router.push("/dashboard")}
        />

        <main
          className={`flex-1 flex flex-col min-h-0 transition-all duration-300 ${
            sidebarCollapsed ? "ml-0" : "ml-[280px]"
          }`}
        >
          {/* Back nav */}
          <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-card/30">
            <button
              onClick={() => router.back()}
              className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back
            </button>
            {file && (
              <>
                <span className="text-muted-foreground/50">/</span>
                <span className="text-sm truncate text-foreground">{file.filename}</span>
              </>
            )}
          </div>

          {/* Chat panel fills remaining height */}
          <div className="flex-1 min-h-0">
            <GroupChatPanel
              groupChatId={groupChatId}
              currentUserId={user.id}
              members={thread.members}
              filename={displayName}
            />
          </div>
        </main>
      </div>
    </div>
  )
}
