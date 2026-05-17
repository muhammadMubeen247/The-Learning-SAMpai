"use client"

import { useState, useEffect, useCallback } from "react"
import { Plus, X, Trash2, MessageSquare, Bold, Italic, Underline, List, ListOrdered, Link, ChevronDown, ChevronUp } from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"
import { useEditor, EditorContent } from "@tiptap/react"
import StarterKit from "@tiptap/starter-kit"
import UnderlineExt from "@tiptap/extension-underline"
import LinkExt from "@tiptap/extension-link"
import Placeholder from "@tiptap/extension-placeholder"
import AnimatedList from "@/components/backgrounds/animated-list"
import { announcementsApi, type Announcement } from "@/api/announcements"
import { normalizeErrorDetail } from "@/lib/error-utils"

type AnnouncementsSectionProps = {
  classroomId: number
  isOwner: boolean
  currentUserId: number
}

// ---------------------------------------------------------------------------
// Rich text editor
// ---------------------------------------------------------------------------

function RichEditor({
  onSubmit,
  onCancel,
  isSubmitting,
}: {
  onSubmit: (html: string) => void
  onCancel: () => void
  isSubmitting: boolean
}) {
  const [linkUrl, setLinkUrl] = useState("")
  const [showLinkInput, setShowLinkInput] = useState(false)
  const [editorEmpty, setEditorEmpty] = useState(true)

  const editor = useEditor({
    extensions: [
      StarterKit.configure({ heading: false, codeBlock: false, code: false, blockquote: false, horizontalRule: false }),
      UnderlineExt,
      LinkExt.configure({ openOnClick: false, HTMLAttributes: { rel: "noopener noreferrer", target: "_blank" } }),
      Placeholder.configure({ placeholder: "Write your announcement here..." }),
    ],
    content: "",
    onUpdate: ({ editor: e }) => setEditorEmpty(e.isEmpty),
    editorProps: {
      attributes: {
        class: "min-h-[90px] max-h-[200px] overflow-y-auto w-full px-3 py-2 text-foreground outline-none tiptap-editor text-sm",
      },
    },
  })

  const applyLink = () => {
    if (!editor) return
    const url = linkUrl.trim()
    if (!url) {
      editor.chain().focus().unsetLink().run()
    } else {
      editor.chain().focus().setLink({ href: url.startsWith("http") ? url : `https://${url}` }).run()
    }
    setLinkUrl("")
    setShowLinkInput(false)
  }

  const handleSubmit = () => {
    if (!editor || editorEmpty) return
    onSubmit(editor.getHTML())
    editor.commands.clearContent()
    setEditorEmpty(true)
  }

  if (!editor) return null

  const toolbarBtn = (active: boolean, onClick: () => void, icon: React.ReactNode, title: string) => (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={`p-1 rounded transition-colors ${
        active
          ? "bg-[color-mix(in_oklab,var(--chart-1),transparent_70%)] text-foreground"
          : "text-muted-foreground hover:text-foreground hover:bg-card/60"
      }`}
    >
      {icon}
    </button>
  )

  return (
    <div className="rounded-lg border border-border bg-background/60 overflow-hidden">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-0.5 px-2 py-1 border-b border-border bg-card/40">
        {toolbarBtn(editor.isActive("bold"), () => editor.chain().focus().toggleBold().run(), <Bold className="size-3" />, "Bold")}
        {toolbarBtn(editor.isActive("italic"), () => editor.chain().focus().toggleItalic().run(), <Italic className="size-3" />, "Italic")}
        {toolbarBtn(editor.isActive("underline"), () => editor.chain().focus().toggleUnderline().run(), <Underline className="size-3" />, "Underline")}
        <div className="w-px h-3.5 bg-border mx-1" />
        {toolbarBtn(editor.isActive("bulletList"), () => editor.chain().focus().toggleBulletList().run(), <List className="size-3" />, "Bullet list")}
        {toolbarBtn(editor.isActive("orderedList"), () => editor.chain().focus().toggleOrderedList().run(), <ListOrdered className="size-3" />, "Numbered list")}
        <div className="w-px h-3.5 bg-border mx-1" />
        <button
          type="button"
          title="Insert link"
          onClick={() => setShowLinkInput((v) => !v)}
          className={`p-1 rounded transition-colors ${
            editor.isActive("link") || showLinkInput
              ? "bg-[color-mix(in_oklab,var(--chart-1),transparent_70%)] text-foreground"
              : "text-muted-foreground hover:text-foreground hover:bg-card/60"
          }`}
        >
          <Link className="size-3" />
        </button>
      </div>

      {/* Link input */}
      <AnimatePresence>
        {showLinkInput && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border bg-card/30">
              <input
                type="url"
                placeholder="https://example.com"
                value={linkUrl}
                onChange={(e) => setLinkUrl(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && applyLink()}
                className="flex-1 text-xs bg-transparent outline-none text-foreground placeholder:text-muted-foreground"
                autoFocus
              />
              <button type="button" onClick={applyLink} className="text-xs px-2 py-0.5 rounded bg-[color-mix(in_oklab,var(--chart-1),transparent_40%)] hover:bg-[color-mix(in_oklab,var(--chart-1),transparent_20%)] transition-colors">Apply</button>
              <button type="button" onClick={() => { setShowLinkInput(false); setLinkUrl("") }} className="text-muted-foreground hover:text-foreground"><X className="size-3" /></button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <EditorContent editor={editor} />

      <div className="flex items-center justify-end gap-2 px-3 py-1.5 border-t border-border bg-card/20">
        <button type="button" onClick={onCancel} className="px-3 py-1 text-xs rounded border border-border bg-card/50 hover:bg-card/70 cursor-pointer transition-colors">Cancel</button>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={isSubmitting || editorEmpty}
          className="px-3 py-1 text-xs rounded bg-[color-mix(in_oklab,var(--chart-1),transparent_10%)] text-foreground hover:shadow-[0_0_12px_rgba(99,102,241,0.3)] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer transition-all"
        >
          {isSubmitting ? "Posting..." : "Post"}
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Render rich HTML from TipTap
// ---------------------------------------------------------------------------

function RichContent({ html }: { html: string }) {
  return (
    <div
      className="rich-content text-foreground text-sm [&_strong]:font-semibold [&_em]:italic [&_u]:underline [&_a]:text-blue-400 [&_a]:underline [&_a]:hover:text-blue-300 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-1 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-1 [&_li]:my-0.5 [&_p]:mb-1 last:[&_p]:mb-0"
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

// ---------------------------------------------------------------------------
// Comment thread
// ---------------------------------------------------------------------------

function CommentThread({
  announcement,
  currentUserId,
  isOwner,
  onCommentAdded,
  onCommentDeleted,
}: {
  announcement: Announcement
  currentUserId: number
  isOwner: boolean
  onCommentAdded: (announcementId: number, comment: Announcement["comments"][0]) => void
  onCommentDeleted: (announcementId: number, commentId: number) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [commentText, setCommentText] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleAddComment = async () => {
    const text = commentText.trim()
    if (!text || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const comment = await announcementsApi.addComment(announcement.id, text)
      onCommentAdded(announcement.id, comment)
      setCommentText("")
    } catch (err: unknown) {
      setError(normalizeErrorDetail(err, "Failed to post comment"))
    } finally {
      setSubmitting(false)
    }
  }

  const handleDeleteComment = async (commentId: number) => {
    try {
      await announcementsApi.deleteComment(announcement.id, commentId)
      onCommentDeleted(announcement.id, commentId)
    } catch (err: unknown) {
      setError(normalizeErrorDetail(err, "Failed to delete comment"))
    }
  }

  const commentCount = announcement.comments.length
  const showList = expanded || commentCount === 0

  return (
    <div className="mt-2.5 pt-2.5 border-t border-border/40">
      {commentCount > 0 && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors mb-1.5"
        >
          <MessageSquare className="size-3" />
          <span>{commentCount} {commentCount === 1 ? "comment" : "comments"}</span>
          {expanded ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
        </button>
      )}

      <AnimatePresence>
        {showList && commentCount > 0 && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden space-y-1.5 mb-2"
          >
            {announcement.comments.map((c) => (
              <div key={c.id} className="flex items-start gap-1.5 group">
                <div className="size-5 rounded-full bg-[color-mix(in_oklab,var(--chart-2),transparent_50%)] flex items-center justify-center text-[9px] font-medium shrink-0 mt-0.5">
                  {c.created_by_username.charAt(0).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <span className="text-[11px] font-medium text-foreground mr-1.5">{c.created_by_username}</span>
                  <span className="text-[11px] text-foreground/80 break-words">{c.content}</span>
                  <span className="text-[10px] text-muted-foreground ml-1.5">{new Date(c.created_at).toLocaleString()}</span>
                </div>
                {(c.created_by_id === currentUserId || isOwner) && (
                  <button type="button" onClick={() => handleDeleteComment(c.id)} className="opacity-0 group-hover:opacity-100 p-0.5 text-muted-foreground hover:text-destructive transition-all shrink-0">
                    <Trash2 className="size-2.5" />
                  </button>
                )}
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Comment input */}
      <div className="flex items-center gap-1.5">
        <input
          type="text"
          value={commentText}
          onChange={(e) => setCommentText(e.target.value)}
          onFocus={() => commentCount > 0 && setExpanded(true)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleAddComment()}
          placeholder="Add a comment..."
          className="flex-1 text-[11px] bg-background/40 border border-border rounded-full px-2.5 py-1 outline-none focus:ring-1 focus:ring-[color-mix(in_oklab,var(--chart-1),transparent_60%)] text-foreground placeholder:text-muted-foreground"
        />
        <button
          type="button"
          onClick={handleAddComment}
          disabled={!commentText.trim() || submitting}
          className="text-[11px] px-2.5 py-1 rounded-full bg-[color-mix(in_oklab,var(--chart-1),transparent_25%)] hover:bg-[color-mix(in_oklab,var(--chart-1),transparent_10%)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {submitting ? "..." : "Post"}
        </button>
      </div>
      {error && <p className="text-[10px] text-destructive mt-1">{error}</p>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Individual announcement card — rendered inside AnimatedList
// ---------------------------------------------------------------------------

function AnnouncementCard({
  ann,
  isOwner,
  currentUserId,
  onDelete,
  onCommentAdded,
  onCommentDeleted,
}: {
  ann: Announcement
  isOwner: boolean
  currentUserId: number
  onDelete: (id: number) => void
  onCommentAdded: (announcementId: number, comment: Announcement["comments"][0]) => void
  onCommentDeleted: (announcementId: number, commentId: number) => void
}) {
  return (
    <div className="rounded-lg border border-border bg-card/50 backdrop-blur-sm p-3.5 group">
      {/* Header */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <div className="size-7 rounded-full bg-[color-mix(in_oklab,var(--chart-1),transparent_50%)] flex items-center justify-center text-xs font-medium shrink-0">
            {ann.created_by_username.charAt(0).toUpperCase()}
          </div>
          <div>
            <p className="text-xs font-medium text-foreground leading-none">{ann.created_by_username}</p>
            <p className="text-[10px] text-muted-foreground mt-0.5">{new Date(ann.created_at).toLocaleString()}</p>
          </div>
        </div>
        {isOwner && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onDelete(ann.id) }}
            className="opacity-0 group-hover:opacity-100 p-1 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all shrink-0"
            title="Delete"
          >
            <Trash2 className="size-3.5" />
          </button>
        )}
      </div>

      <RichContent html={ann.content} />

      <CommentThread
        announcement={ann}
        currentUserId={currentUserId}
        isOwner={isOwner}
        onCommentAdded={onCommentAdded}
        onCommentDeleted={onCommentDeleted}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function AnnouncementsSection({
  classroomId,
  isOwner,
  currentUserId,
}: AnnouncementsSectionProps) {
  const [announcements, setAnnouncements] = useState<Announcement[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showEditor, setShowEditor] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const fetchAnnouncements = useCallback(async () => {
    try {
      const data = await announcementsApi.list(classroomId)
      setAnnouncements(data)
    } catch (err: unknown) {
      setError(normalizeErrorDetail(err, "Failed to load announcements"))
    } finally {
      setLoading(false)
    }
  }, [classroomId])

  useEffect(() => {
    void fetchAnnouncements()
  }, [fetchAnnouncements])

  const handlePost = async (html: string) => {
    setIsSubmitting(true)
    setError(null)
    try {
      const created = await announcementsApi.create(classroomId, html)
      setAnnouncements((prev) => [created, ...prev])
      setShowEditor(false)
    } catch (err: unknown) {
      setError(normalizeErrorDetail(err, "Failed to post announcement"))
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDelete = async (announcementId: number) => {
    try {
      await announcementsApi.delete(announcementId)
      setAnnouncements((prev) => prev.filter((a) => a.id !== announcementId))
    } catch (err: unknown) {
      setError(normalizeErrorDetail(err, "Failed to delete announcement"))
    }
  }

  const handleCommentAdded = (announcementId: number, comment: Announcement["comments"][0]) => {
    setAnnouncements((prev) =>
      prev.map((a) => a.id === announcementId ? { ...a, comments: [...a.comments, comment] } : a)
    )
  }

  const handleCommentDeleted = (announcementId: number, commentId: number) => {
    setAnnouncements((prev) =>
      prev.map((a) =>
        a.id === announcementId ? { ...a, comments: a.comments.filter((c) => c.id !== commentId) } : a
      )
    )
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-3 flex-none">
        <h2 className="text-lg font-semibold text-foreground">Announcements</h2>
        {isOwner && (
          <button
            type="button"
            onClick={() => setShowEditor((v) => !v)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer transition-colors text-xs"
          >
            {showEditor ? <X className="size-3.5" /> : <Plus className="size-3.5" />}
            <span>{showEditor ? "Cancel" : "New"}</span>
          </button>
        )}
      </div>

      {/* Editor (slides in above the list) */}
      <AnimatePresence>
        {showEditor && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="flex-none mb-3 overflow-hidden"
          >
            <RichEditor
              onSubmit={handlePost}
              onCancel={() => setShowEditor(false)}
              isSubmitting={isSubmitting}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Global error */}
      {error && (
        <div className="flex-none mb-2 px-3 py-1.5 rounded border border-destructive/40 bg-destructive/10 text-xs text-destructive">
          {error}
        </div>
      )}

      {/* List container — fills remaining height, scrollable via AnimatedList */}
      <div className="flex-1 min-h-0 rounded-xl border border-border/60 bg-card/20 backdrop-blur-sm overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <div className="size-5 rounded-full border-2 border-t-transparent border-[color-mix(in_oklab,var(--chart-1),transparent_30%)] animate-spin" />
          </div>
        ) : announcements.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            {isOwner && !showEditor ? (
              <button
                type="button"
                onClick={() => setShowEditor(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer transition-colors text-sm"
              >
                <Plus className="size-4" />
                <span>Add Announcement</span>
              </button>
            ) : (
              <p className="text-sm text-muted-foreground">No announcements yet</p>
            )}
          </div>
        ) : (
          <AnimatedList
            items={announcements.map((a) => String(a.id))}
            renderItem={(id) => {
              const ann = announcements.find((a) => String(a.id) === id)
              if (!ann) return null
              return (
                <AnnouncementCard
                  ann={ann}
                  isOwner={isOwner}
                  currentUserId={currentUserId}
                  onDelete={handleDelete}
                  onCommentAdded={handleCommentAdded}
                  onCommentDeleted={handleCommentDeleted}
                />
              )
            }}
            enableArrowNavigation={false}
            showGradients
            displayScrollbar
            className="h-full"
          />
        )}
      </div>
    </div>
  )
}
