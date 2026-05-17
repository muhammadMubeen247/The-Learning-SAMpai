"use client"

import { useState, useEffect } from "react"
import { motion } from "framer-motion"
import type { CardPublic, ReviewResult } from "@/api/flashcards"

const TYPE_COLORS: Record<string, string> = {
  definition: "border-blue-400/40 bg-blue-500/10 text-blue-600 dark:text-blue-300",
  concept:    "border-purple-400/40 bg-purple-500/10 text-purple-600 dark:text-purple-300",
  example:    "border-amber-400/40 bg-amber-500/10 text-amber-600 dark:text-amber-300",
  formula:    "border-emerald-400/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300",
}

const REVIEW_OPTS = [
  { result: "forgot" as ReviewResult, label: "Forgot", key: "1", cls: "border-red-400/40 bg-red-500/10 text-red-500 hover:bg-red-500/20" },
  { result: "unsure" as ReviewResult, label: "Unsure", key: "2", cls: "border-amber-400/40 bg-amber-500/10 text-amber-500 hover:bg-amber-500/20" },
  { result: "know"   as ReviewResult, label: "Know",   key: "3", cls: "border-emerald-400/40 bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20" },
]

export interface StackSummary { know: number; unsure: number; forgot: number }

interface Props {
  cards: CardPublic[]
  onReview: (card: CardPublic, result: ReviewResult) => void
  onComplete: (summary: StackSummary) => void
}

const CARD_H   = 260
const MAX_BG   = 3

export function FlashcardStack({ cards, onReview, onComplete }: Props) {
  const [stackIds, setStackIds]       = useState(() => cards.map((c) => c.id))
  const [flipped, setFlipped]         = useState(false)
  const [reviewedCount, setReviewed]  = useState(0)
  const [summary, setSummary]         = useState<StackSummary>({ know: 0, unsure: 0, forgot: 0 })
  const [animating, setAnimating]     = useState(false)

  const cardById   = Object.fromEntries(cards.map((c) => [c.id, c]))
  const totalCards = cards.length
  const topId      = stackIds[stackIds.length - 1]
  const visibleIds = stackIds.slice(-(MAX_BG + 1))

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null
      if (t?.tagName === "INPUT" || t?.tagName === "TEXTAREA" || t?.isContentEditable) return
      if (e.key === " ") { e.preventDefault(); if (!flipped && !animating) setFlipped(true) }
      if (flipped && !animating) {
        if (e.key === "1") handleReview("forgot")
        else if (e.key === "2") handleReview("unsure")
        else if (e.key === "3") handleReview("know")
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [flipped, animating]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleReview(result: ReviewResult) {
    if (animating) return
    const card = cardById[topId]
    if (!card) return

    setAnimating(true)
    const newSummary = { ...summary, [result]: summary[result] + 1 }
    setSummary(newSummary)
    onReview(card, result)

    const newCount = reviewedCount + 1
    setReviewed(newCount)

    if (newCount >= totalCards) {
      setTimeout(() => onComplete(newSummary), 420)
      return
    }

    setTimeout(() => {
      setStackIds((prev) => {
        const arr = [...prev]
        const top = arr.pop()!
        arr.unshift(top)
        return arr
      })
      setFlipped(false)
      setTimeout(() => setAnimating(false), 260)
    }, 230)
  }

  const pct = totalCards > 0 ? (reviewedCount / totalCards) * 100 : 0

  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-6 px-6 py-4 min-h-0">

      {/* Progress */}
      <div className="w-full max-w-lg space-y-1.5 shrink-0">
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>{reviewedCount} of {totalCards} reviewed</span>
          <span>{totalCards - reviewedCount} left</span>
        </div>
        <div className="h-1.5 rounded-full bg-border/30 overflow-hidden">
          <div
            className="h-full bg-chart-1/60 rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Stack */}
      <div
        className="relative w-full max-w-lg flex-none mx-auto"
        style={{ height: CARD_H }}
      >
        {visibleIds.map((id, visIdx) => {
          const isTop      = id === topId
          const posFromTop = visibleIds.length - 1 - visIdx
          const rotZ       = isTop ? 0 : posFromTop % 2 === 0 ? posFromTop * 4 : -(posFromTop * 4)
          const scl        = 1 - posFromTop * 0.045
          const yOff       = posFromTop * 6

          return (
            <motion.div
              key={id}
              className="absolute inset-0"
              style={{ zIndex: visIdx, transformOrigin: "50% 105%" }}
              animate={{ rotateZ: rotZ, scale: scl, y: yOff }}
              transition={{ type: "spring", stiffness: 280, damping: 22 }}
            >
              {isTop ? (
                <div style={{ width: "100%", height: "100%", perspective: 1400 }}>
                  <motion.div
                    className="relative w-full h-full"
                    style={{ transformStyle: "preserve-3d" }}
                    animate={{ rotateY: flipped ? 180 : 0 }}
                    transition={{ duration: 0.42, ease: "easeInOut" }}
                    onClick={() => { if (!flipped && !animating) setFlipped(true) }}
                  >
                    {/* Front */}
                    <div
                      className="absolute inset-0 rounded-2xl border border-border/70 bg-card/85 backdrop-blur-md flex flex-col items-center justify-center gap-4 text-center overflow-hidden cursor-pointer p-8 shadow-lg"
                      style={{ backfaceVisibility: "hidden" }}
                    >
                      <div className="absolute inset-0 bg-gradient-to-br from-blue-500/10 via-transparent to-violet-500/10 rounded-2xl pointer-events-none" />
                      {cardById[id]?.card_type && (
                        <span className={`relative z-10 text-[11px] font-medium px-2.5 py-0.5 rounded-full border capitalize ${TYPE_COLORS[cardById[id].card_type] ?? "border-border/40 text-muted-foreground"}`}>
                          {cardById[id].card_type}
                        </span>
                      )}
                      <p className="relative z-10 text-base font-medium text-foreground leading-relaxed max-w-sm">
                        {cardById[id]?.front}
                      </p>
                      <p className="relative z-10 text-xs text-muted-foreground/40">click to reveal</p>
                    </div>

                    {/* Back */}
                    <div
                      className="absolute inset-0 rounded-2xl border border-chart-1/50 bg-card/85 backdrop-blur-md flex flex-col gap-4 overflow-hidden p-6 shadow-lg"
                      style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}
                    >
                      <div className="absolute inset-0 bg-gradient-to-br from-chart-1/15 via-transparent to-chart-2/10 rounded-2xl pointer-events-none" />
                      <p className="flex-1 min-h-0 text-sm text-foreground leading-relaxed overflow-y-auto relative z-10">
                        {cardById[id]?.back}
                      </p>
                      <div className="shrink-0 flex gap-2 relative z-10">
                        {REVIEW_OPTS.map(({ result, label, key, cls }) => (
                          <button
                            key={result}
                            type="button"
                            onClick={(e) => { e.stopPropagation(); handleReview(result) }}
                            className={`flex-1 py-2 rounded-xl border text-sm font-medium transition-colors cursor-pointer ${cls}`}
                          >
                            {label} <span className="opacity-40 text-xs">{key}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  </motion.div>
                </div>
              ) : (
                <div className="w-full h-full rounded-2xl border border-border/50 bg-card/60 backdrop-blur-sm shadow-md" />
              )}
            </motion.div>
          )
        })}
      </div>

      {/* Hint */}
      <p className="shrink-0 text-[11px] text-muted-foreground/40 text-center">
        Space to flip · 1 Forgot · 2 Unsure · 3 Know
      </p>
    </div>
  )
}
