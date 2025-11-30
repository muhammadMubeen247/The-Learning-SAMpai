"use client"

import { Menu, ChevronRight } from "lucide-react"
import { useRouter } from "next/navigation"
import { ThemeToggle } from "@/components/theme/theme-toggle"
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu"

type ClassroomHeaderProps = {
  classroomName: string
  username: string
  onMenuClick: () => void
  onLogout: () => void
  folderName?: string
  classroomId?: number
}

export default function ClassroomHeader({
  classroomName,
  username,
  onMenuClick,
  onLogout,
  folderName,
  classroomId,
}: ClassroomHeaderProps) {
  const router = useRouter()

  return (
    <div className="fixed top-0 left-0 right-0 z-50 h-16 border-b border-border bg-background/80 backdrop-blur-xl">
      <div className="flex items-center justify-between h-full px-4">
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={onMenuClick}
            className="p-2 rounded-md hover:bg-card/50 cursor-pointer transition-colors"
            aria-label="Toggle sidebar"
          >
            <Menu className="size-5 text-foreground" />
          </button>
          {folderName ? (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => classroomId && router.push(`/classroom/${classroomId}`)}
                className="text-lg font-semibold text-foreground hover:text-foreground/80 transition-colors cursor-pointer"
              >
                {classroomName}
              </button>
              <ChevronRight className="size-4 text-muted-foreground" />
              <span className="text-lg font-semibold text-foreground">{folderName}</span>
            </div>
          ) : (
            <h1 className="text-lg font-semibold text-foreground">{classroomName}</h1>
          )}
        </div>
        <div className="flex items-center space-x-2">
          <ThemeToggle />
          <DropdownMenu>
            <DropdownMenuTrigger>
              <div className="flex items-center gap-2 cursor-pointer">
                <div
                  aria-hidden
                  className="size-8 rounded-full bg-gradient-to-br from-chart-1 to-chart-2 ring-1 ring-border/50 shadow-inner"
                />
                <span className="text-sm text-foreground/80">{username}</span>
              </div>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-72">
              <div className="flex flex-col items-center gap-3 px-4 py-4">
                <div
                  aria-hidden
                  className="size-16 rounded-full bg-gradient-to-br from-chart-1 to-chart-2 ring-1 ring-border/50 shadow-inner"
                />
                <span className="text-base font-semibold text-foreground">{username}</span>
              </div>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={onLogout}
                className="cursor-pointer text-red-500 focus:text-red-500 hover:text-red-500"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  className="size-4 mr-2"
                  aria-hidden
                >
                  <path d="M16 13v-2H7V8l-5 4 5 4v-3h9zM20 3h-8v2h8v14h-8v2h8a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2z" />
                </svg>
                <span>Log out</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </div>
  )
}

