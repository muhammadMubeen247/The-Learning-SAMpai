"use client"

import { useEffect, useRef, useState } from "react"
import { motion } from "framer-motion"
import { type CardPublic, type ReviewResult } from "@/api/flashcards"

const TYPE_COLORS: Record<string, string> = {
  definition: "border-blue-400/40 bg-blue-500/10 text-blue-600 dark:text-blue-300",
  concept: "border-purple-400/40 bg-purple-500/10 text-purple-600 dark:text-purple-300",
  example: "border-amber-400/40 bg-amber-500/10 text-amber-600 dark:text-amber-300",
  formula: "border-emerald-400/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300",
}

const REVIEW_BUTTONS: { result: ReviewResult; label: string; key: string; cls: string }[] = [
  {
    result: "forgot",
    label: "Forgot",
    key: "1",
    cls: "border-red-400/40 bg-red-500/10 text-red-500 hover:bg-red-500/20",
  },
  {
    result: "unsure",
    label: "Unsure",
    key: "2",
    cls: "border-amber-400/40 bg-amber-500/10 text-amber-500 hover:bg-amber-500/20",
  },
  {
    result: "know",
    label: "Know",
    key: "3",
    cls: "border-emerald-400/40 bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20",
  },
]

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

  useEffect(() => {
    setFace("front")
  }, [card.id])

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
      {/* Header row */}
      <div className="flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            {index + 1} / {total}
          </span>
          {/* Progress dots */}
          <div className="flex gap-0.5">
            {Array.from({ length: Math.min(total, 10) }).map((_, i) => (
              <span
                key={i}
                className={`block w-1.5 h-1.5 rounded-full transition-colors ${
                  i === index ? "bg-chart-1" : i < index ? "bg-chart-1/30" : "bg-border/40"
                }`}
              />
            ))}
            {total > 10 && <span className="text-[10px] text-muted-foreground ml-1">…</span>}
          </div>
        </div>
        <span
          className={`capitalize text-[11px] font-medium px-2 py-0.5 rounded-full border ${
            TYPE_COLORS[card.card_type] ?? "border-border/40 bg-card/20 text-muted-foreground"
          }`}
        >
          {card.card_type}
        </span>
      </div>

      {/* 3D flip card */}
      <div
        className="flex-1 min-h-0 cursor-pointer select-none"
        style={{ perspective: "1200px" }}
        onClick={() => setFace((f) => (f === "front" ? "back" : "front"))}
      >
        <motion.div
          className="relative w-full h-full"
          style={{ transformStyle: "preserve-3d" }}
          animate={{ rotateY: face === "front" ? 0 : 180 }}
          transition={{ duration: 0.45, ease: "easeInOut" }}
        >
          {/* Front */}
          <div
            className="absolute inset-0 rounded-2xl border border-border/40 bg-card/30 backdrop-blur-md p-6 flex flex-col items-center justify-center gap-3 text-center overflow-hidden"
            style={{ backfaceVisibility: "hidden" }}
          >
            <div className="absolute inset-0 bg-gradient-to-br from-blue-500/5 via-transparent to-violet-500/5 pointer-events-none rounded-2xl" />
            <p className="text-base font-medium text-foreground leading-relaxed relative z-10">
              {card.front}
            </p>
            <p className="text-xs text-muted-foreground/50 relative z-10">tap to reveal</p>
          </div>

          {/* Back */}
          <div
            className="absolute inset-0 rounded-2xl border border-chart-1/30 bg-card/30 backdrop-blur-md p-5 flex flex-col gap-3 overflow-hidden"
            style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}
          >
            <div className="absolute inset-0 bg-gradient-to-br from-chart-1/8 via-transparent to-chart-2/8 pointer-events-none rounded-2xl" />

            {/* Answer text */}
            <div className="flex-1 min-h-0 overflow-y-auto relative z-10">
              <p className="text-sm text-foreground leading-relaxed">{card.back}</p>
            </div>

            {/* Review controls */}
            <div className="shrink-0 relative z-10 space-y-2">
              <p className="text-[11px] text-muted-foreground/60 text-center">
                Box {card.box} → {previewBox(card.box, "know")} if Know
              </p>
              <div className="flex gap-2">
                {REVIEW_BUTTONS.map(({ result, label, key, cls }) => (
                  <button
                    key={result}
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      onReview(result)
                    }}
                    className={`flex-1 py-2 rounded-xl border text-sm font-medium transition-colors cursor-pointer ${cls}`}
                  >
                    {label}{" "}
                    <span className="opacity-40 text-xs">{key}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </motion.div>
      </div>

      {/* Nav hint */}
      <p className="shrink-0 text-center text-[11px] text-muted-foreground/50">
        ← → browse · Space flip · 1 / 2 / 3 rate
      </p>
    </div>
  )
}
