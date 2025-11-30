"use client"

import { useState, useEffect, useMemo } from "react"
import { useRouter } from "next/navigation"
import { Home, ChevronDown } from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"
import AnimatedList from "@/components/backgrounds/animated-list"
import DotGrid from "@/components/backgrounds/dot-grid"
import API from "@/api/axios"
import { useCurrentUser, type CurrentUser } from "@/hooks/use-current-user"
import { cn } from "@/lib/utils"

type Classroom = {
  id: number
  name: string
  description: string | null
  code: string
  owner_id: number
}

type ClassroomSidebarProps = {
  collapsed: boolean
  currentClassroomId: number
  onHomeClick: () => void
}

export default function ClassroomSidebar({
  collapsed,
  currentClassroomId,
  onHomeClick,
}: ClassroomSidebarProps) {
  const router = useRouter()
  const { user } = useCurrentUser()
  const [classrooms, setClassrooms] = useState<Classroom[]>([])
  const [loading, setLoading] = useState(true)
  const [joinedExpanded, setJoinedExpanded] = useState(true)

  const fetchClassrooms = async () => {
    setLoading(true)
    try {
      const res = await API.get<Classroom[]>("/classrooms/")
      setClassrooms(res.data)
    } catch (err: any) {
      if (err?.response?.status === 401) {
        if (typeof window !== "undefined") {
          localStorage.removeItem("token")
          localStorage.removeItem("user")
        }
        router.push("/login")
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void fetchClassrooms()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const joinedClassrooms = useMemo(() => {
    if (!user) return []
    return classrooms.filter((c) => c.owner_id !== user.id)
  }, [classrooms, user])

  const joinedNames = joinedClassrooms.map((c) => c.name)

  const handleClassroomSelect = (name: string, index: number) => {
    const selectedClassroom = joinedClassrooms[index]
    if (selectedClassroom) {
      router.push(`/classroom/${selectedClassroom.id}`)
    }
  }

  return (
    <motion.aside
      initial={false}
      animate={{
        x: collapsed ? -280 : 0,
        opacity: collapsed ? 0 : 1,
      }}
      transition={{ duration: 0.3, ease: "easeInOut" }}
      className="fixed left-0 top-16 w-[280px] h-[calc(100vh-4rem)] shrink-0 border-r bg-card/70 backdrop-blur-md border-border overflow-hidden flex flex-col z-40"
      style={{ pointerEvents: collapsed ? "none" : "auto" }}
    >
      {/* Ambient Glow */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(60%_40%_at_40%_10%,color-mix(in_oklab,var(--chart-2),transparent_85%)_0%,transparent_60%)]"
      />

      {/* DotGrid */}
      <div className="absolute inset-0 -z-0 opacity-35 pointer-events-none">
        <DotGrid
          className="absolute inset-0 p-0 pointer-events-none"
          dotSize={10}
          gap={18}
          baseColor="#334155"
          activeColor="#64748b"
          proximity={120}
          shockRadius={220}
          shockStrength={4}
          resistance={700}
          returnDuration={1.4}
        />
      </div>

      {/* Home Button */}
      <div className="relative z-10 px-4 py-4 border-b border-border">
        <button
          type="button"
          onClick={onHomeClick}
          className="flex items-center gap-2 px-3 py-2 rounded-md hover:bg-card/50 cursor-pointer transition-colors w-full"
        >
          <Home className="size-4 text-foreground" />
          <span className="text-sm font-medium text-foreground">Home</span>
        </button>
      </div>

      {/* Joined Section */}
      <div className="relative z-10 flex-1 min-h-0 flex flex-col">
        <button
          type="button"
          onClick={() => setJoinedExpanded(!joinedExpanded)}
          className="flex items-center justify-between px-4 py-3 border-b border-border hover:bg-card/30 cursor-pointer transition-colors"
        >
          <div className="flex items-center gap-2">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="size-4 text-foreground"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden
            >
              <path d="M16 11a4 4 0 1 0-8 0 4 4 0 0 0 8 0Z"></path>
              <path
                fillRule="evenodd"
                d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm0 18a7.963 7.963 0 0 1-5.657-2.343A8 8 0 1 1 12 20Z"
                clipRule="evenodd"
              ></path>
            </svg>
            <span className="text-sm font-medium text-foreground">joined</span>
          </div>
          <ChevronDown
            className={cn(
              "size-4 text-foreground transition-transform",
              joinedExpanded && "rotate-180"
            )}
            aria-hidden
          />
        </button>

        <AnimatePresence>
          {joinedExpanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="flex-1 min-h-0 overflow-hidden"
            >
              {loading ? (
                <div className="p-4 text-sm text-muted-foreground">Loading...</div>
              ) : joinedNames.length === 0 ? (
                <div className="p-4 text-sm text-muted-foreground text-center">
                  No classrooms joined yet
                </div>
              ) : (
                <div className="h-full px-2 py-3 overflow-hidden">
                  <AnimatedList
                    items={joinedNames}
                    onItemSelect={handleClassroomSelect}
                    className="w-full h-full overflow-y-auto"
                    itemClassName="border border-border rounded-lg cursor-pointer"
                    displayScrollbar
                  />
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.aside>
  )
}

