"use client"

import { useEffect, useRef, useState } from "react"
import { motion } from "framer-motion"
import { BrainCircuit } from "lucide-react"
import { FlashcardStack, type StackSummary } from "./FlashcardStack"
import { FlashcardHistory } from "./FlashcardHistory"
import {
  generateDeck,
  getDeck,
  getDeckHistory,
  getDueCards,
  reviewCard,
  type CardPublic,
  type DeckHistoryItem,
  type ReviewResult,
} from "@/api/flashcards"

type PanelState = "idle" | "generating" | "reviewing" | "done" | "error"

interface Props {
  fileId: number
  canFlashcard: boolean
}

const POLL_INTERVAL_MS = 2000
const POLL_TIMEOUT_MS  = 120_000

const BOX_COLORS = ["bg-red-400", "bg-orange-400", "bg-yellow-400", "bg-blue-400", "bg-emerald-400"]

export function FlashcardPanel({ fileId, canFlashcard }: Props) {
  const [state,     setState]     = useState<PanelState>("idle")
  const [deckId,    setDeckId]    = useState<number | null>(null)
  const [cards,     setCards]     = useState<CardPublic[]>([])
  const [cardCount, setCardCount] = useState<"10" | "20" | "30">("20")
  const [history,   setHistory]   = useState<DeckHistoryItem[]>([])
  const [boxCounts, setBoxCounts] = useState<Record<string, number> | null>(null)
  const [dueCount,  setDueCount]  = useState(0)
  const [errorMsg,  setErrorMsg]  = useState<string | null>(null)
  const [summary,   setSummary]   = useState<StackSummary>({ know: 0, unsure: 0, forgot: 0 })
  const [showHistory, setShowHistory] = useState(false)

  const pollStartRef = useRef<number>(0)

  function refreshHistory() {
    getDeckHistory(fileId)
      .then((h) => { setHistory(h.items); setBoxCounts(h.box_counts ?? null) })
      .catch(() => {})
  }

  useEffect(() => {
    if (!canFlashcard) return
    getDeckHistory(fileId)
      .then((h) => {
        setHistory(h.items)
        setBoxCounts(h.box_counts ?? null)
        if (h.has_open_deck && h.open_deck_id != null) {
          resumeDeck(h.open_deck_id)
        } else {
          getDueCards(fileId).then((d) => setDueCount(d.total_due)).catch(() => {})
        }
      })
      .catch(() => {})
  }, [fileId, canFlashcard]) // eslint-disable-line react-hooks/exhaustive-deps

  async function resumeDeck(id: number) {
    setDeckId(id)
    try {
      const detail = await getDeck(id)
      if (detail.status === "ready" && detail.cards?.length) {
        setCards(detail.cards); setSummary({ know: 0, unsure: 0, forgot: 0 }); setState("reviewing")
      } else if (detail.status === "pending" || detail.status === "generating") {
        pollStartRef.current = Date.now(); setState("generating")
      } else if (detail.status === "failed") {
        setErrorMsg(detail.error_msg ?? "Generation failed."); setState("error")
      }
    } catch { setState("idle") }
  }

  useEffect(() => {
    if (state !== "generating" || deckId == null) return
    const interval = setInterval(async () => {
      if (Date.now() - pollStartRef.current > POLL_TIMEOUT_MS) {
        clearInterval(interval); setErrorMsg("Timed out. Please try again."); setState("error"); return
      }
      try {
        const detail = await getDeck(deckId)
        if (detail.status === "ready" && detail.cards?.length) {
          clearInterval(interval); setCards(detail.cards); setSummary({ know: 0, unsure: 0, forgot: 0 }); setState("reviewing"); refreshHistory()
        } else if (detail.status === "failed") {
          clearInterval(interval); setErrorMsg(detail.error_msg ?? "Generation failed."); setState("error")
        }
      } catch {}
    }, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [state, deckId]) // eslint-disable-line react-hooks/exhaustive-deps

  async function handleGenerate() {
    setErrorMsg(null)
    try {
      const res = await generateDeck(fileId, { card_count: Number(cardCount) as 10 | 20 | 30 })
      setDeckId(res.deck_id); pollStartRef.current = Date.now(); setState("generating")
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail ?? "Failed to start generation.")
    }
  }

  async function handleStartDueReview() {
    try {
      const due = await getDueCards(fileId)
      if (!due.cards.length) return
      setCards(due.cards); setSummary({ know: 0, unsure: 0, forgot: 0 }); setDeckId(null); setState("reviewing")
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail ?? "Failed to load due cards.")
    }
  }

  async function handleStackReview(card: CardPublic, result: ReviewResult) {
    try { await reviewCard(card.id, result) } catch {}
  }

  function handleStackComplete(stackSummary: StackSummary) {
    setSummary(stackSummary)
    setState("done")
    refreshHistory()
    getDueCards(fileId).then((d) => setDueCount(d.total_due)).catch(() => {})
  }

  function handleReset() {
    setDeckId(null); setCards([]); setErrorMsg(null)
    setSummary({ know: 0, unsure: 0, forgot: 0 }); setState("idle")
    refreshHistory()
    getDueCards(fileId).then((d) => setDueCount(d.total_due)).catch(() => {})
  }

  // Mastery bar derived from boxCounts
  const totalInBoxes = boxCounts ? Object.values(boxCounts).reduce((a, b) => a + b, 0) : 0

  if (!canFlashcard) {
    return (
      <div className="flex-1 flex items-center justify-center p-6">
        <p className="text-muted-foreground text-sm text-center">
          Flashcards will be available once this file finishes processing.
        </p>
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">

      {/* ── IDLE ── */}
      {state === "idle" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-8 px-8 py-6">

          {/* Icon + heading */}
          <div className="text-center space-y-2">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl border border-border/40 bg-card/40 backdrop-blur-sm mb-1">
              <BrainCircuit className="w-7 h-7 text-chart-1" />
            </div>
            <p className="text-base font-semibold text-foreground">Flashcards</p>
            <p className="text-xs text-muted-foreground/70 max-w-xs">
              {history.length > 0 ? "Spaced-repetition review from this document." : "AI-generated from this document. Review with spaced repetition."}
            </p>
          </div>

          {/* Mastery bar — only if cards have been studied */}
          {boxCounts && totalInBoxes > 0 && (
            <div className="w-full max-w-xs space-y-1.5">
              <div className="flex h-2 rounded-full overflow-hidden gap-px">
                {[1, 2, 3, 4, 5].map((box) => {
                  const count = boxCounts[String(box)] ?? 0
                  const pct   = totalInBoxes > 0 ? (count / totalInBoxes) * 100 : 0
                  return (
                    <div
                      key={box}
                      className={`${BOX_COLORS[box - 1]} transition-all`}
                      style={{ width: `${pct}%` }}
                      title={`Box ${box}: ${count} card${count !== 1 ? "s" : ""}`}
                    />
                  )
                })}
              </div>
              <div className="flex justify-between text-[10px] text-muted-foreground/50">
                <span>Learning</span><span>Mastered</span>
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="w-full max-w-xs space-y-3">
            {/* Due review — primary action if any due */}
            {dueCount > 0 && (
              <button
                type="button"
                onClick={handleStartDueReview}
                className="w-full py-3 rounded-xl border border-chart-1/40 bg-chart-1/15 text-sm font-medium text-chart-1 hover:bg-chart-1/25 transition-colors cursor-pointer"
              >
                Review {dueCount} due card{dueCount !== 1 ? "s" : ""}
              </button>
            )}

            {/* Divider */}
            {dueCount > 0 && (
              <div className="flex items-center gap-3">
                <div className="flex-1 h-px bg-border/30" />
                <span className="text-[10px] text-muted-foreground/40">or generate new</span>
                <div className="flex-1 h-px bg-border/30" />
              </div>
            )}

            {/* Card count + generate */}
            <div className="space-y-2.5">
              <div className="flex gap-2">
                {(["10", "20", "30"] as const).map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => setCardCount(n)}
                    className={`flex-1 py-2 rounded-xl border text-sm font-medium transition-all cursor-pointer ${
                      cardCount === n
                        ? "border-chart-1/60 bg-chart-1/20 text-foreground"
                        : "border-border/40 bg-card/20 text-muted-foreground hover:border-border/60 hover:text-foreground"
                    }`}
                  >
                    {n}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={handleGenerate}
                className="w-full py-2.5 rounded-xl bg-chart-1/80 hover:bg-chart-1 text-foreground text-sm font-medium transition-colors cursor-pointer"
              >
                Generate {cardCount} cards
              </button>
            </div>

            {/* Error */}
            {errorMsg && (
              <p className="text-xs text-destructive text-center">{errorMsg}</p>
            )}
          </div>

          {/* Past decks — collapsible */}
          {history.length > 0 && (
            <div className="w-full max-w-xs">
              <button
                type="button"
                onClick={() => setShowHistory((v) => !v)}
                className="w-full text-[11px] text-muted-foreground/50 hover:text-muted-foreground transition-colors cursor-pointer text-center"
              >
                {showHistory ? "Hide history" : `${history.length} past deck${history.length !== 1 ? "s" : ""}`}
              </button>
              {showHistory && (
                <div className="mt-2 max-h-40 overflow-y-auto">
                  <FlashcardHistory items={history} boxCounts={boxCounts} />
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── GENERATING ── */}
      {state === "generating" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-4">
          <div className="flex gap-1.5 items-center">
            {[0, 1, 2].map((i) => (
              <motion.span
                key={i}
                className="block w-2 h-2 rounded-full bg-chart-1/70"
                animate={{ y: [0, -6, 0] }}
                transition={{ duration: 0.9, delay: i * 0.18, repeat: Infinity, ease: "easeInOut" }}
              />
            ))}
          </div>
          <p className="text-sm text-muted-foreground">Generating flashcards…</p>
          <p className="text-xs text-muted-foreground/50">This may take up to a minute.</p>
        </div>
      )}

      {/* ── REVIEWING ── */}
      {state === "reviewing" && cards.length > 0 && (
        <FlashcardStack
          cards={cards}
          onReview={handleStackReview}
          onComplete={handleStackComplete}
        />
      )}

      {/* ── DONE ── */}
      {state === "done" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-6 px-8">
          <div className="text-center">
            <p className="text-lg font-semibold text-foreground">Session complete</p>
            <p className="text-xs text-muted-foreground/60 mt-1">{cards.length} cards reviewed</p>
          </div>

          <div className="grid grid-cols-3 gap-3 w-full max-w-xs">
            {[
              { label: "Know",   count: summary.know,   cls: "border-emerald-400/30 bg-emerald-500/10", textCls: "text-emerald-500" },
              { label: "Unsure", count: summary.unsure, cls: "border-amber-400/30 bg-amber-500/10",   textCls: "text-amber-500" },
              { label: "Forgot", count: summary.forgot, cls: "border-red-400/30 bg-red-500/10",       textCls: "text-red-500" },
            ].map(({ label, count, cls, textCls }) => (
              <div key={label} className={`rounded-2xl border ${cls} p-4 text-center backdrop-blur-sm`}>
                <p className={`text-2xl font-bold ${textCls}`}>{count}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
              </div>
            ))}
          </div>

          <div className="flex flex-col gap-2 w-full max-w-xs">
            {dueCount > 0 && (
              <button type="button" onClick={handleStartDueReview}
                className="w-full py-2.5 rounded-xl border border-chart-1/40 bg-chart-1/10 text-sm font-medium text-chart-1 hover:bg-chart-1/20 transition-colors cursor-pointer">
                Review {dueCount} due card{dueCount !== 1 ? "s" : ""}
              </button>
            )}
            <button type="button" onClick={handleGenerate}
              className="w-full py-2.5 rounded-xl bg-chart-1/80 hover:bg-chart-1 text-foreground text-sm font-medium transition-colors cursor-pointer">
              New deck
            </button>
            <button type="button" onClick={handleReset}
              className="w-full py-2 rounded-xl text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer">
              ← Back
            </button>
          </div>
        </div>
      )}

      {/* ── ERROR ── */}
      {state === "error" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-3">
          {errorMsg && <p className="text-xs text-destructive text-center max-w-xs">{errorMsg}</p>}
          <button type="button" onClick={handleReset}
            className="px-6 py-2.5 rounded-xl border border-border/40 bg-card/30 text-sm text-foreground hover:bg-card/50 cursor-pointer transition-colors">
            Back to setup
          </button>
        </div>
      )}

    </div>
  )
}
