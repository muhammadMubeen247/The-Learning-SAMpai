"use client"

import { ChevronRight } from "lucide-react"
import AnimatedList from "@/components/backgrounds/animated-list"
import DotGrid from "@/components/backgrounds/dot-grid"
import { cn } from "@/lib/utils"

type Classroom = {
  id: number
  name: string
  description: string | null
  code: string
  owner_id: number
}

type LeftPaneProps = {
  classrooms: string[]
  classroomObjects?: Classroom[]
  onSelect?: (name: string, index: number) => void
  onExpand?: () => void
  className?: string
  expanded?: boolean
  showExpandButton?: boolean
}

export function LeftPane({
  classrooms,
  onSelect,
  onExpand,
  className,
  expanded = false,
  showExpandButton = true,
}: LeftPaneProps) {
  const empty = !classrooms || classrooms.length === 0

  return (
    <aside
      className={cn(
        "relative h-full shrink-0 border-r bg-card/70 backdrop-blur-md border-border overflow-hidden flex flex-col",
        expanded ? "w-full" : "w-[360px]",
        className,
      )}
      aria-label="Joined classrooms"
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

      {/* Header */}
      <div className="relative z-10 flex items-center gap-2 px-4 py-4 border-b border-border">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="size-5 text-foreground"
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
        <span className="text-sm font-medium text-foreground">Joined</span>
      </div>

      {/* Content */}
      <div className="relative z-10 flex-1 min-h-0 px-2 py-3 overflow-hidden">
        {empty ? (
          <div className="h-full grid place-items-center text-center">
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">No classrooms joined yet</p>
              <p className="text-xs text-muted-foreground/70">Join a classroom from the center buttons</p>
            </div>
          </div>
        ) : (
          <AnimatedList
            items={classrooms}
            onItemSelect={(name, index) => onSelect?.(name, index)}
            className="w-full h-full overflow-y-auto"
            itemClassName="border border-border rounded-lg cursor-pointer"
            displayScrollbar
          />
        )}
      </div>

      {/* Expand Button */}
      {showExpandButton && (
        <button
          type="button"
          onClick={onExpand}
          className="relative z-10 mx-2 mb-3 group mt-auto flex items-center justify-between px-5 py-4 rounded-lg border border-border bg-card/70 text-foreground/85 hover:text-foreground transition-all cursor-pointer hover:shadow-[0_0_28px_rgba(99,102,241,0.35)]"
        >
          <span className="text-sm">Expand</span>
          <ChevronRight className="size-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
        </button>
      )}
    </aside>
  )
}

export default LeftPane
