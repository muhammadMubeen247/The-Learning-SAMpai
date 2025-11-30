"use client"

import type React from "react"
import { useState, useEffect, useRef, useMemo } from "react"
import dynamic from "next/dynamic"
import { Plus, LogIn, X } from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"
import Navbar from "@/components/landingpage/navbar"
import { useRouter } from "next/navigation"
import LeftPane from "./left-pane"
import RightPane from "./right-pane"
import Orb from "@/components/backgrounds/orb"
import API from "@/api/axios"
import { useCurrentUser, type CurrentUser } from "@/hooks/use-current-user"
import { normalizeErrorDetail } from "@/lib/error-utils"
import { useTheme } from "@/hooks/use-theme"

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

export default function Dashboard() {
  const [classrooms, setClassrooms] = useState<Classroom[]>([])
  const { user, loading: userLoading, setUser } = useCurrentUser()
  const { theme } = useTheme()
  const hasLoadedUser = !userLoading
  const router = useRouter()
  const onLogout = () => {
    if (typeof window !== "undefined") {
      localStorage.removeItem("token")
      localStorage.removeItem("user")
    }
    setUser(null as unknown as CurrentUser | null)
    setTimeout(() => router.push("/login"), 200)
  }

  // Modal visibility + form state
  const [showCreate, setShowCreate] = useState(false)
  const [showJoin, setShowJoin] = useState(false)
  const [createName, setCreateName] = useState("")
  const [createDesc, setCreateDesc] = useState("")
  const [joinCode, setJoinCode] = useState("")

  const [isSubmitting, setIsSubmitting] = useState(false)
  const [loadingClassrooms, setLoadingClassrooms] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const openCreate = () => setShowCreate(true)
  const openJoin = () => setShowJoin(true)

  const fetchClassrooms = async () => {
    setLoadingClassrooms(true)
    setError(null)
    try {
      const res = await API.get<Classroom[]>("/classrooms/")
      setClassrooms(res.data)
    } catch (err: any) {
      if (err?.response?.status === 401) {
        // token invalid or expired
        if (typeof window !== "undefined") {
          localStorage.removeItem("token")
          localStorage.removeItem("user")
        }
        router.push("/login")
      } else {
        setError("Failed to load classrooms. Please try again.")
        // eslint-disable-next-line no-console
        console.error("Error loading classrooms", err)
      }
    } finally {
      setLoadingClassrooms(false)
    }
  }

  useEffect(() => {
    if (!hasLoadedUser) return
    // if no user and no token, redirect to login
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null
    if (!user || !token) {
      router.push("/login")
      return
    }
    // Fetch classrooms immediately when user is loaded
    if (classrooms.length === 0 && !loadingClassrooms) {
      void fetchClassrooms()
    }
  }, [hasLoadedUser, user, router])

  const { createdClassrooms, joinedClassrooms } = useMemo(() => {
    if (!user) return { createdClassrooms: [] as Classroom[], joinedClassrooms: [] as Classroom[] }
    const created = classrooms.filter((c) => c.owner_id === user.id)
    const joined = classrooms.filter((c) => c.owner_id !== user.id)
    return {
      createdClassrooms: created,
      joinedClassrooms: joined,
    }
  }, [classrooms, user])

  const createdNames = createdClassrooms.map((c) => c.name)
  const joinedNames = joinedClassrooms.map((c) => c.name)

  const hasCreated = createdNames.length > 0

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const name = createName.trim()
    if (!name || isSubmitting) return
    setIsSubmitting(true)
    setError(null)
    try {
      await API.post("/classrooms/create", {
        name,
        description: createDesc.trim() || null,
      })
      setCreateName("")
      setCreateDesc("")
      setShowCreate(false)
      await fetchClassrooms()
    } catch (err: any) {
      if (err?.response?.status === 401) {
        if (typeof window !== "undefined") {
          localStorage.removeItem("token")
          localStorage.removeItem("user")
        }
        router.push("/login")
      } else {
        const detail = err?.response?.data?.detail
        setError(normalizeErrorDetail(detail, "Failed to create classroom."))
        // eslint-disable-next-line no-console
        console.error("Error creating classroom", err)
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleJoinSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const code = joinCode.trim()
    if (!code || isSubmitting) return
    setIsSubmitting(true)
    setError(null)
    try {
      const response = await API.post<Classroom>(`/classrooms/join/${code}`)
      const classroomId = response.data.id
      setJoinCode("")
      setShowJoin(false)
      // Immediately redirect to the classroom page
      router.push(`/classroom/${classroomId}`)
    } catch (err: any) {
      if (err?.response?.status === 401) {
        if (typeof window !== "undefined") {
          localStorage.removeItem("token")
          localStorage.removeItem("user")
        }
        router.push("/login")
      } else {
        const detail = err?.response?.data?.detail
        setError(normalizeErrorDetail(detail, "Failed to join classroom."))
        // eslint-disable-next-line no-console
        console.error("Error joining classroom", err)
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  // Close modals on Escape key
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setShowCreate(false)
        setShowJoin(false)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  const plasmaColor = theme === "dark" ? "#60a5fa" : "#3b82f6"
  
  // Theme-appropriate colors for Squares background
  const borderColor = theme === "dark" ? "rgba(147, 197, 253, 0.3)" : "rgba(56, 189, 248, 0.4)"
  const hoverFillColor = theme === "dark" ? "rgba(147, 197, 253, 0.1)" : "rgba(56, 189, 248, 0.15)"
  const leftPaneWidth = 360
  const [viewportWidth, setViewportWidth] = useState(0)
  const [expandingPane, setExpandingPane] = useState<null | "joined" | "created">(null)
  const expandTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const expansionDuration = 650

  useEffect(() => {
    const updateViewport = () => setViewportWidth(window.innerWidth)
    updateViewport()
    window.addEventListener("resize", updateViewport)
    return () => window.removeEventListener("resize", updateViewport)
  }, [])

  const triggerExpand = (pane: "joined" | "created") => {
    if (expandingPane) return
    setExpandingPane(pane)
    expandTimeoutRef.current = setTimeout(() => {
      router.push(pane === "joined" ? "/joined" : "/created")
    }, expansionDuration)
  }

  useEffect(() => {
    return () => {
      if (expandTimeoutRef.current) {
        clearTimeout(expandTimeoutRef.current)
      }
    }
  }, [])

  const navRef = useRef<HTMLDivElement | null>(null)
  const [navH, setNavH] = useState<number>(64)

  useEffect(() => {
    if (!navRef.current) return
    const el = navRef.current
    const ro = new ResizeObserver((entries) => {
      const h = entries[0]?.contentRect.height || 64
      setNavH(h)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  return (
    <div className="relative min-h-screen w-screen overflow-hidden bg-background">

      <div ref={navRef} className="relative z-10">
        <Navbar variant="minimal" username={user?.username ?? ""} onLogout={onLogout} />
      </div>

      {/* Main section fills everything below navbar */}
      <main
        className="absolute left-0 right-0 bottom-0 flex z-10"
        style={{ top: `${navH}px` }}
      >
        {/* Left Pane */}
        <LeftPane
          classrooms={joinedNames}
          classroomObjects={joinedClassrooms}
          onSelect={(name, index) => {
            const classroom = joinedClassrooms[index]
            if (classroom) {
              router.push(`/classroom/${classroom.id}`)
            }
          }}
          onExpand={() => triggerExpand("joined")}
          className="rounded-none h-full"
        />

        {/* Center region with two big Orb buttons */}
        <section className="relative flex-1 flex items-center justify-center overflow-hidden">
          {/* Squares Background */}
          <div className="absolute inset-0 opacity-60 pointer-events-none z-0">
            <Squares
              speed={0.5}
              squareSize={40}
              direction="diagonal"
              borderColor={borderColor}
              hoverFillColor={hoverFillColor}
            />
          </div>
          
          <div className={`relative z-10 flex items-center justify-center transition-all duration-300 ${hasCreated ? 'gap-10 xl:gap-12' : 'gap-16 xl:gap-20'}`}>
            <button
              type="button"
              onClick={openJoin}
              className="relative size-[19rem] xl:size-[21rem] rounded-full cursor-pointer group"
              aria-label="Join classroom"
            >
              <Orb hue={30} rotateOnHover hoverIntensity={0.6} />
              <div className="pointer-events-none absolute inset-0 grid place-items-center">
                <div className="flex items-center gap-3 text-foreground/95">
                  <LogIn className="size-7 xl:size-8" />
                  <span className="text-xl xl:text-2xl font-medium">Join</span>
                </div>
              </div>
            </button>

            <button
              type="button"
              onClick={openCreate}
              className="relative size-[19rem] xl:size-[21rem] rounded-full cursor-pointer group"
              aria-label="Create classroom"
            >
              <Orb hue={300} rotateOnHover hoverIntensity={0.6} />
              <div className="pointer-events-none absolute inset-0 grid place-items-center">
                <div className="flex items-center gap-3 text-foreground/95">
                  <Plus className="size-7 xl:size-8" />
                  <span className="text-xl xl:text-2xl font-medium">Create</span>
                </div>
              </div>
            </button>
          </div>
        </section>

        {/* Right Pane */}
        <AnimatePresence mode="wait">
          {hasCreated && (
            <motion.div
              key="right-pane"
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 8 }}
              transition={{ duration: 0.15, ease: "easeOut" }}
              className="shrink-0 h-full"
            >
              <RightPane
                classrooms={createdNames}
                classroomObjects={createdClassrooms}
                onSelect={(name, index) => {
                  const classroom = createdClassrooms[index]
                  if (classroom) {
                    router.push(`/classroom/${classroom.id}`)
                  }
                }}
                onExpand={() => triggerExpand("created")}
                className="rounded-none h-full"
              />
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {/* Modals */}
      <AnimatePresence>
        {(showCreate || showJoin) && (
          <>
            {/* Backdrop blur */}
            <motion.div
              key="backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="fixed inset-0 z-30 bg-background/50 backdrop-blur-md"
              aria-hidden
            />
            {/* Card */}
            <motion.div
              key="card"
              initial={{ opacity: 0, scale: 0.96, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8 }}
              transition={{ type: "spring", stiffness: 260, damping: 22 }}
              className="fixed inset-0 z-40 grid place-items-center p-4"
              role="dialog"
              aria-modal="true"
            >
              <div className="relative w-full max-w-md rounded-2xl border border-border bg-card/70 backdrop-blur-xl shadow-2xl">
                {/* Ambient glow */}
                <div
                  aria-hidden
                  className="pointer-events-none absolute -inset-1 rounded-2xl blur-2xl opacity-40"
                  style={{
                    background:
                      "radial-gradient(60% 40% at 50% 0%, color-mix(in_oklab, var(--chart-1), transparent 80%) 0%, transparent 70%)",
                  }}
                />
                <div className="relative p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-medium text-foreground">
                      {showCreate ? "Create Classroom" : "Join Classroom"}
                    </h3>
                    <button
                      type="button"
                      onClick={() => {
                        setShowCreate(false)
                        setShowJoin(false)
                      }}
                      className="p-2 rounded-md border border-border/60 bg-card/60 hover:bg-card/80 cursor-pointer"
                      aria-label="Close"
                    >
                      <X className="size-4" />
                    </button>
                  </div>

                  {showCreate ? (
                    <form onSubmit={handleCreateSubmit} className="space-y-4">
                      <div className="space-y-2">
                        <label className="text-sm text-muted-foreground">Classroom name</label>
                        <input
                          value={createName}
                          onChange={(e) => setCreateName(e.target.value)}
                          className="w-full rounded-md border border-border bg-background/60 px-3 py-2 text-foreground outline-none focus:ring-2 focus:ring-[color-mix(in_oklab,var(--chart-1),transparent_70%)]"
                          placeholder="e.g. Algebra 101"
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-sm text-muted-foreground">Description</label>
                        <textarea
                          value={createDesc}
                          onChange={(e) => setCreateDesc(e.target.value)}
                          rows={3}
                          className="w-full rounded-md border border-border bg-background/60 px-3 py-2 text-foreground outline-none focus:ring-2 focus:ring-[color-mix(in_oklab,var(--chart-2),transparent_70%)]"
                          placeholder="Optional details"
                        />
                      </div>
                      <div className="flex items-center justify-end gap-3 pt-2">
                        <button
                          type="button"
                          onClick={() => setShowCreate(false)}
                          className="px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer"
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          className="px-4 py-2 rounded-md bg-[color-mix(in_oklab,var(--chart-1),transparent_10%)] text-foreground hover:shadow-[0_0_26px_rgba(99,102,241,0.35)] cursor-pointer disabled:opacity-70"
                          disabled={isSubmitting}
                        >
                          {isSubmitting ? "Creating..." : "Create"}
                        </button>
                      </div>
                    </form>
                  ) : (
                    <form onSubmit={handleJoinSubmit} className="space-y-4">
                      <div className="space-y-2">
                        <label className="text-sm text-muted-foreground">Classroom code</label>
                        <input
                          value={joinCode}
                          onChange={(e) => setJoinCode(e.target.value)}
                          className="w-full rounded-md border border-border bg-background/60 px-3 py-2 text-foreground outline-none focus:ring-2 focus:ring-[color-mix(in_oklab,var(--chart-1),transparent_70%)]"
                          placeholder="e.g. X1Y2Z3"
                        />
                      </div>
                      <div className="flex items-center justify-end gap-3 pt-2">
                        <button
                          type="button"
                          onClick={() => setShowJoin(false)}
                          className="px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer"
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          className="px-4 py-2 rounded-md bg-[color-mix(in_oklab,var(--chart-2),transparent_10%)] text-foreground hover:shadow-[0_0_26px_rgba(99,102,241,0.35)] cursor-pointer disabled:opacity-70"
                          disabled={isSubmitting}
                        >
                          {isSubmitting ? "Joining..." : "Join"}
                        </button>
                      </div>
                    </form>
                  )}
                  {error && (
                    <p className="mt-4 text-sm text-destructive/90">
                      {error}
                    </p>
                  )}
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {expandingPane && (
          <motion.div
            key={expandingPane}
            initial={{
              width: leftPaneWidth,
              x:
                expandingPane === "created"
                  ? (viewportWidth || leftPaneWidth) - leftPaneWidth
                  : 0,
            }}
            animate={{
              width: viewportWidth || leftPaneWidth,
              x: 0,
            }}
            exit={{ opacity: 0 }}
            transition={{ duration: expansionDuration / 1000, ease: [0.22, 0.8, 0.3, 0.98] }}
            className="fixed z-40 top-0 bottom-0 bg-background/95 backdrop-blur-2xl pointer-events-none"
            style={{
              left: 0,
              top: navH,
              height: `calc(100vh - ${navH}px)`,
              transformOrigin: expandingPane === "joined" ? "left center" : "right center",
            }}
          >
            {expandingPane === "joined"
              ? (
                <LeftPane
                  classrooms={joinedNames}
                  classroomObjects={joinedClassrooms}
                  onSelect={(name, index) => {
                    const classroom = joinedClassrooms[index]
                    if (classroom) {
                      router.push(`/classroom/${classroom.id}`)
                    }
                  }}
                  expanded
                  showExpandButton={false}
                  className="rounded-none h-full"
                />
              )
              : (
                <RightPane
                  classrooms={createdNames}
                  classroomObjects={createdClassrooms}
                  onSelect={(name, index) => {
                    const classroom = createdClassrooms[index]
                    if (classroom) {
                      router.push(`/classroom/${classroom.id}`)
                    }
                  }}
                  expanded
                  showExpandButton={false}
                  className="rounded-none h-full"
                />
              )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
