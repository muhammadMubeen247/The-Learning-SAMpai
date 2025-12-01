"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { motion, AnimatePresence } from "framer-motion"
import { Plus, X } from "lucide-react"
import Folder from "@/components/backgrounds/folder"
import Orb from "@/components/backgrounds/orb"
import API from "@/api/axios"
import { normalizeErrorDetail } from "@/lib/error-utils"
import { useTheme } from "@/hooks/use-theme"
import { LoadingOrb } from "@/components/ui/liquid-orb-loader"

type FolderType = {
  id: number
  name: string
  files: unknown[]
}

type FoldersSectionProps = {
  classroomId: number
  isOwner: boolean
  onFolderCreated?: () => void
}

export default function FoldersSection({
  classroomId,
  isOwner,
  onFolderCreated,
}: FoldersSectionProps) {
  const router = useRouter()
  const { theme } = useTheme()
  const [folders, setFolders] = useState<FolderType[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingProgress, setLoadingProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [folderName, setFolderName] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)

  const folderColor = theme === "dark" ? "#93C5FD" : "#38BDF8"

  const fetchFolders = async () => {
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
      const res = await API.get<FolderType[]>(`/folders/classroom/${classroomId}`)
      setLoadingProgress(70)
      setFolders(res.data)
      setLoadingProgress(100)
    } catch (err: any) {
      if (err?.response?.status === 401) {
        if (typeof window !== "undefined") {
          localStorage.removeItem("token")
          localStorage.removeItem("user")
        }
        window.location.href = "/login"
      } else {
        setError("Failed to load folders")
      }
    } finally {
      clearInterval(progressInterval)
      setLoading(false)
      setTimeout(() => setLoadingProgress(0), 500)
    }
  }

  useEffect(() => {
    void fetchFolders()
  }, [classroomId])

  const handleCreateFolder = async (e: React.FormEvent) => {
    e.preventDefault()
    const name = folderName.trim()
    if (!name || isSubmitting) return

    setIsSubmitting(true)
    setError(null)
    try {
      await API.post(`/folders/classroom/${classroomId}`, { name })
      setFolderName("")
      setShowCreateModal(false)
      await fetchFolders()
      onFolderCreated?.()
    } catch (err: any) {
      if (err?.response?.status === 401) {
        if (typeof window !== "undefined") {
          localStorage.removeItem("token")
          localStorage.removeItem("user")
        }
        window.location.href = "/login"
      } else if (err?.response?.status === 403) {
        setError("Only the owner can create folders")
      } else {
        const detail = err?.response?.data?.detail
        setError(normalizeErrorDetail(detail, "Failed to create folder"))
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  const hasFolders = folders.length > 0
  const showCreateButton = isOwner

  return (
    <div className="p-4 sm:p-6 md:p-8 pt-20 sm:pt-24 md:pt-28 min-h-full w-full overflow-x-hidden">
      <div className="max-w-[1400px] mx-auto w-full">
        {loading ? (
          <div className="flex items-center justify-center py-16 min-h-[60vh]">
            <LoadingOrb 
              progress={loadingProgress}
              size="lg"
              message="Loading folders..."
              showProgress={true}
            />
          </div>
        ) : !hasFolders && !showCreateButton ? (
          <div className="text-center py-16">
            <p className="text-muted-foreground">No folders yet</p>
          </div>
        ) : !hasFolders && showCreateButton ? (
          // Center the create button when no folders exist
          <div className="flex items-center justify-center min-h-[60vh]">
            <div className="group flex flex-col items-center gap-6">
              <button
                type="button"
                onClick={() => setShowCreateModal(true)}
                className="relative size-[160px] rounded-full cursor-pointer"
                aria-label="Create folder"
              >
                <Orb hue={300} rotateOnHover hoverIntensity={0.6} />
                <div className="pointer-events-none absolute inset-0 grid place-items-center">
                  <Plus className="size-12 text-foreground/95" />
                </div>
              </button>
              <p className="text-lg text-foreground text-center font-semibold tracking-wide">
                Create Folder
              </p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 sm:gap-x-8 md:gap-x-10 gap-y-20 sm:gap-y-24">
            {/* Folders */}
            {folders.map((folder) => (
              <div
                key={folder.id}
                className="group flex flex-col items-center cursor-pointer"
                onClick={() => router.push(`/classroom/${classroomId}/folder/${folder.id}`)}
              >
                <div className="relative flex items-center justify-center w-full h-[150px] mb-2 overflow-visible">
                  <div className="absolute inset-0 blur-2xl bg-gradient-to-br from-chart-1/30 to-chart-2/30 rounded-full pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity" />
                  <div className="relative z-10 flex items-center justify-center">
                    <Folder
                      color={folderColor}
                      size={1.4}
                      description=""
                      showPapers={true}
                      className="cursor-pointer transition-transform"
                    />
                  </div>
                </div>
                <p className="text-sm text-foreground text-center font-semibold tracking-wide leading-tight px-2 line-clamp-2 min-h-[2.5rem] flex items-center justify-center mt-1">
                  {folder.name}
                </p>
              </div>
            ))}

            {/* Create Folder Button (Owner Only) - Positioned after folders in grid */}
            {showCreateButton && (
              <div className="group flex flex-col items-center">
                <div className="relative flex items-center justify-center w-full h-[150px] mb-2">
                  <button
                    type="button"
                    onClick={() => setShowCreateModal(true)}
                    className="relative size-[110px] rounded-full cursor-pointer"
                    aria-label="Create folder"
                  >
                    <Orb hue={300} rotateOnHover hoverIntensity={0.6} />
                    <div className="pointer-events-none absolute inset-0 grid place-items-center">
                      <Plus className="size-7 text-foreground/95" />
                    </div>
                  </button>
                </div>
                <p className="text-sm text-foreground text-center font-semibold tracking-wide leading-tight px-2 min-h-[2.5rem] flex items-center justify-center mt-1">
                  Create Folder
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Create Folder Modal */}
      <AnimatePresence>
        {showCreateModal && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="fixed inset-0 z-30 bg-background/50 backdrop-blur-md"
              aria-hidden
              onClick={() => setShowCreateModal(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8 }}
              transition={{ type: "spring", stiffness: 260, damping: 22 }}
              className="fixed inset-0 z-40 grid place-items-center p-4"
              role="dialog"
              aria-modal="true"
            >
              <div className="relative w-full max-w-md rounded-2xl border border-border bg-card/70 backdrop-blur-xl shadow-2xl">
                <div className="relative p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-medium text-foreground">Create Folder</h3>
                    <button
                      type="button"
                      onClick={() => setShowCreateModal(false)}
                      className="p-2 rounded-md border border-border/60 bg-card/60 hover:bg-card/80 cursor-pointer"
                      aria-label="Close"
                    >
                      <X className="size-4" />
                    </button>
                  </div>

                  <form onSubmit={handleCreateFolder} className="space-y-4">
                    <div className="space-y-2">
                      <label className="text-sm text-muted-foreground">Folder name</label>
                      <input
                        value={folderName}
                        onChange={(e) => setFolderName(e.target.value)}
                        className="w-full rounded-md border border-border bg-background/60 px-3 py-2 text-foreground outline-none focus:ring-2 focus:ring-[color-mix(in_oklab,var(--chart-1),transparent_70%)]"
                        placeholder="e.g. Lecture Notes"
                        autoFocus
                      />
                    </div>
                    {error && (
                      <p className="text-sm text-destructive/90">{error}</p>
                    )}
                    <div className="flex items-center justify-end gap-3 pt-2">
                      <button
                        type="button"
                        onClick={() => setShowCreateModal(false)}
                        className="px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        className="px-4 py-2 rounded-md bg-[color-mix(in_oklab,var(--chart-1),transparent_10%)] text-foreground hover:shadow-[0_0_26px_rgba(99,102,241,0.35)] cursor-pointer disabled:opacity-70"
                        disabled={isSubmitting || !folderName.trim()}
                      >
                        {isSubmitting ? "Creating..." : "Create"}
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}

