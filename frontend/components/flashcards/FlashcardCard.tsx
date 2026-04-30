"use client"

import { useEffect, useRef, useState } from "react"
import { motion } from "framer-motion"
import { Button } from "@/components/ui/button"
import { type CardPublic, type ReviewResult } from "@/api/flashcards"

const TYPE_COLORS: Record<string, string> = {
  definition: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  concept: "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300",
  example: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  formula: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
}

function previewBox(box: number, result: ReviewResult): number {
  if (result === "know") return Math.min(box + 1, 5)
  if (result === "unsure") return Math.max(box - 1, 1)
  return 1
}

interface Props {
  card: CardPublic
  index: number
  total: number
  onReview: (result: ReviewResult) => void
  onPrev: () => void
  onNext: () => void
}

export function FlashcardCard({ card, index, total, onReview, onPrev, onNext }: Props) {
  const [face, setFace] = useState<"front" | "back">("front")
  const faceRef = useRef(face)
  faceRef.current = face

  // Reset to front when card changes
  useEffect(() => {
    setFace("front")
  }, [card.id])

  // Keyboard shortcuts
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null
      const tag = target?.tagName
      if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) return

      if (e.key === " ") {
        e.preventDefault()
        setFace((f) => (f === "front" ? "back" : "front"))
      } else if (e.key === "ArrowLeft") {
        e.preventDefault()
        onPrev()
      } else if (e.key === "ArrowRight") {
        e.preventDefault()
        onNext()
      } else if (faceRef.current === "back") {
        if (e.key === "1") onReview("forgot")
        else if (e.key === "2") onReview("unsure")
        else if (e.key === "3") onReview("know")
      }
    }
    window.addEventListener("keydown", handleKey)
    return () => window.removeEventListener("keydown", handleKey)
  }, [onReview, onPrev, onNext])

  return (
    <div className="flex-1 flex flex-col min-h-0 gap-3">
      {/* Progress */}
      <div className="flex items-center justify-between text-xs text-muted-foreground shrink-0">
        <span>Card {index + 1} of {total}</span>
        <span className="capitalize">
          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${TYPE_COLORS[card.card_type]}`}>
            {card.card_type}
          </span>
        </span>
      </div>

      {/* 3D flip card */}
      <div
        className="flex-1 min-h-0 cursor-pointer"
        style={{ perspective: "1000px" }}
        onClick={() => setFace((f) => (f === "front" ? "back" : "front"))}
      >
        <motion.div
          className="relative w-full h-full"
          style={{ transformStyle: "preserve-3d" }}
          animate={{ rotateY: face === "front" ? 0 : 180 }}
          transition={{ duration: 0.45, ease: "easeInOut" }}
        >
          {/* Front face */}
          <div
            className="absolute inset-0 rounded-xl border border-border bg-card/70 backdrop-blur-sm p-6 flex flex-col items-center justify-center gap-3 text-center"
            style={{ backfaceVisibility: "hidden" }}
          >
            <p className="text-base font-medium text-foreground leading-relaxed">{card.front}</p>
            <p className="text-xs text-muted-foreground mt-2">
              Space or tap to reveal
            </p>
          </div>

          {/* Back face */}
          <div
            className="absolute inset-0 rounded-xl border border-primary/30 bg-card/70 backdrop-blur-sm p-6 flex flex-col gap-4"
            style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}
          >
            <p className="flex-1 text-sm text-foreground leading-relaxed overflow-y-auto">{card.back}</p>
            <div className="shrink-0 space-y-2">
              <p className="text-[11px] text-muted-foreground text-center">
                Box {card.box} → Box {previewBox(card.box, "know")} if Know
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="flex-1 border-red-400 text-red-600 hover:bg-red-50 dark:hover:bg-red-950"
                  onClick={(e) => { e.stopPropagation(); onReview("forgot") }}
                >
                  Forgot <span className="ml-1 text-[10px] opacity-50">1</span>
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="flex-1 border-amber-400 text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-950"
                  onClick={(e) => { e.stopPropagation(); onReview("unsure") }}
                >
                  Unsure <span className="ml-1 text-[10px] opacity-50">2</span>
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="flex-1 border-emerald-400 text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-950"
                  onClick={(e) => { e.stopPropagation(); onReview("know") }}
                >
                  Know <span className="ml-1 text-[10px] opacity-50">3</span>
                </Button>
              </div>
            </div>
          </div>
        </motion.div>
      </div>

      {/* Nav hint */}
      <p className="shrink-0 text-center text-[11px] text-muted-foreground/60">
        ← → browse · Space to flip · 1/2/3 to rate
      </p>
    </div>
  )
}
