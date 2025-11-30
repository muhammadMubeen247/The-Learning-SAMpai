"use client"

import { useState } from "react"
import { Plus, X } from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"

type Announcement = {
  id: string
  content: string
  createdAt: Date
}

type AnnouncementsSectionProps = {
  isOwner: boolean
}

export default function AnnouncementsSection({ isOwner }: AnnouncementsSectionProps) {
  const [announcements, setAnnouncements] = useState<Announcement[]>([])
  const [showAddModal, setShowAddModal] = useState(false)
  const [announcementText, setAnnouncementText] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleAddAnnouncement = (e: React.FormEvent) => {
    e.preventDefault()
    const content = announcementText.trim()
    if (!content || isSubmitting) return

    setIsSubmitting(true)
    const newAnnouncement: Announcement = {
      id: Date.now().toString(),
      content,
      createdAt: new Date(),
    }
    setAnnouncements((prev) => [newAnnouncement, ...prev])
    setAnnouncementText("")
    setShowAddModal(false)
    setIsSubmitting(false)
  }

  return (
    <div className="relative z-10 p-4 sm:p-6 md:p-8 min-h-[300px] w-full overflow-x-hidden">
      <div className="max-w-[1600px] mx-auto w-full">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-semibold text-foreground">Announcements</h2>
          {isOwner && announcements.length > 0 && (
            <button
              type="button"
              onClick={() => setShowAddModal(true)}
              className="flex items-center gap-2 px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer transition-colors"
            >
              <Plus className="size-4" />
              <span className="text-sm">Add</span>
            </button>
          )}
        </div>

        {announcements.length === 0 ? (
          <div className="flex items-center justify-center py-16">
            {isOwner ? (
              <button
                type="button"
                onClick={() => setShowAddModal(true)}
                className="flex items-center gap-2 px-6 py-3 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer transition-colors"
              >
                <Plus className="size-5" />
                <span>Add Announcement</span>
              </button>
            ) : (
              <p className="text-muted-foreground">No announcements yet</p>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            {announcements.map((announcement) => (
              <motion.div
                key={announcement.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="p-4 rounded-lg border border-border bg-card/50 backdrop-blur-sm"
              >
                <p className="text-foreground whitespace-pre-wrap">{announcement.content}</p>
                <p className="text-xs text-muted-foreground mt-2">
                  {announcement.createdAt.toLocaleString()}
                </p>
              </motion.div>
            ))}
          </div>
        )}
      </div>

      {/* Add Announcement Modal */}
      <AnimatePresence>
        {showAddModal && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="fixed inset-0 z-30 bg-background/50 backdrop-blur-md"
              aria-hidden
              onClick={() => setShowAddModal(false)}
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
                    <h3 className="text-lg font-medium text-foreground">Add Announcement</h3>
                    <button
                      type="button"
                      onClick={() => setShowAddModal(false)}
                      className="p-2 rounded-md border border-border/60 bg-card/60 hover:bg-card/80 cursor-pointer"
                      aria-label="Close"
                    >
                      <X className="size-4" />
                    </button>
                  </div>

                  <form onSubmit={handleAddAnnouncement} className="space-y-4">
                    <div className="space-y-2">
                      <label className="text-sm text-muted-foreground">Announcement</label>
                      <textarea
                        value={announcementText}
                        onChange={(e) => setAnnouncementText(e.target.value)}
                        rows={4}
                        className="w-full rounded-md border border-border bg-background/60 px-3 py-2 text-foreground outline-none focus:ring-2 focus:ring-[color-mix(in_oklab,var(--chart-1),transparent_70%)]"
                        placeholder="Enter announcement text..."
                        autoFocus
                      />
                    </div>
                    <div className="flex items-center justify-end gap-3 pt-2">
                      <button
                        type="button"
                        onClick={() => setShowAddModal(false)}
                        className="px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        className="px-4 py-2 rounded-md bg-[color-mix(in_oklab,var(--chart-1),transparent_10%)] text-foreground hover:shadow-[0_0_26px_rgba(99,102,241,0.35)] cursor-pointer disabled:opacity-70"
                        disabled={isSubmitting || !announcementText.trim()}
                      >
                        {isSubmitting ? "Adding..." : "Add"}
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

