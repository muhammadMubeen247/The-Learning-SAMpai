"use client"
import { useState, useEffect, useRef, useMemo } from "react"
import { useRouter, usePathname } from "next/navigation"
import Navbar from "@/components/landingpage/navbar"
import Folder from "@/components/backgrounds/folder"
import Plasma from "@/components/backgrounds/plasma"
import { useTheme } from "@/hooks/use-theme"
import API from "@/api/axios"
import { useCurrentUser, type CurrentUser } from "@/hooks/use-current-user"

type Classroom = {
  id: number
  name: string
  description: string | null
  code: string
  owner_id: number
}

export default function CreatedPage() {
  const router = useRouter()
  const pathname = usePathname()
  const { theme } = useTheme()
  const { user, loading: userLoading, setUser } = useCurrentUser()
  const [classrooms, setClassrooms] = useState<Classroom[]>([])
  const [loadingClassrooms, setLoadingClassrooms] = useState(false)
  const [error, setError] = useState<string | null>(null)

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

  const fetchClassrooms = async () => {
    setLoadingClassrooms(true)
    setError(null)
    try {
      const res = await API.get<Classroom[]>("/classrooms/")
      setClassrooms(res.data)
    } catch (err: any) {
      if (err?.response?.status === 401) {
        if (typeof window !== "undefined") {
          localStorage.removeItem("token")
          localStorage.removeItem("user")
        }
        setUser(null as unknown as CurrentUser | null)
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
    if (userLoading) return
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null
    if (!user || !token) {
      router.push("/login")
      return
    }
    void fetchClassrooms()
  }, [userLoading, user, router])

  const createdClassrooms = useMemo(
    () => (user ? classrooms.filter((c) => c.owner_id === user.id) : []),
    [classrooms, user],
  )

  const plasmaColor = theme === "dark" ? "#60a5fa" : "#3b82f6"
  const folderColor = theme === "dark" ? "#93C5FD" : "#38BDF8"

  return (
    <div className="relative min-h-screen bg-background overflow-x-hidden">
      <div ref={navRef}>
        <Navbar
          variant="minimal"
          username={user?.username ?? ""}
          onLogout={() => {
            if (typeof window !== "undefined") {
              localStorage.removeItem("token")
              localStorage.removeItem("user")
            }
            setUser(null as unknown as CurrentUser | null)
            router.push("/login")
          }}
          actions={
            <button
              type="button"
              onClick={() => router.push("/dashboard")}
              className="px-4 py-2 rounded-md border border-border/70 bg-card/60 hover:bg-card/80 cursor-pointer text-sm font-medium text-foreground"
            >
              Dashboard
            </button>
          }
        />
      </div>
      <div className="absolute inset-0 opacity-80">
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

      <main
        className="relative z-10 flex flex-col"
        style={{ paddingTop: `${navH + 32}px` }}
      >
        <div className="px-8 pb-24 w-full">
          <h1 className="text-4xl font-bold text-foreground mb-20">Created Classrooms</h1>

          <div className="w-full max-w-[1600px] mx-auto px-16">
            {loadingClassrooms ? (
              <p className="mt-16 text-sm text-muted-foreground">Loading classrooms...</p>
            ) : createdClassrooms.length === 0 ? (
              <p className="mt-16 text-sm text-muted-foreground">You haven&apos;t created any classrooms yet.</p>
            ) : (
              <div className="grid grid-cols-3 gap-x-16 gap-y-24">
                {createdClassrooms.map((classroom) => (
                  <div
                    key={classroom.id}
                    className="group flex flex-col items-center gap-4 w-full cursor-pointer"
                    onClick={() => router.push(`/classroom/${classroom.id}`)}
                  >
                    <div className="relative flex items-center justify-center w-full h-[180px]">
                      <div className="absolute inset-0 blur-2xl bg-gradient-to-br from-chart-1/30 to-chart-2/30 rounded-full pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity" />
                      <Folder
                        color={folderColor}
                        size={1.8}
                        description={classroom.description ?? ""}
                        showPapers={true}
                        allowPaperPopOut={false}
                        className="cursor-pointer transition-transform relative z-10"
                      />
                    </div>
                    <p className="text-lg text-foreground text-center font-semibold tracking-wide leading-tight min-h-[2.5rem] px-2">
                      {classroom.name}
                    </p>
                  </div>
                ))}
              </div>
            )}
            {error && (
              <p className="mt-4 text-sm text-destructive/90">
                {error}
              </p>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
