"use client"

import { useState } from "react"
import { UserPlus } from "lucide-react"
import { InviteDialog } from "./invite-dialog"

type Props = {
  fileId: number
  classroomId: number
}

export function InviteButton({ fileId }: Props) {
  const [open, setOpen] = useState(false)

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-full bg-violet-600/10 border border-violet-500/30 px-3 py-1 text-xs font-medium text-violet-400 hover:bg-violet-600/20 transition-colors cursor-pointer"
        title="Invite classmates to a group chat"
      >
        <UserPlus className="w-3.5 h-3.5" />
        Group Chat
      </button>

      {open && (
        <InviteDialog
          fileId={fileId}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  )
}
