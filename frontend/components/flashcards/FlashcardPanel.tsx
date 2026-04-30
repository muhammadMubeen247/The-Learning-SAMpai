"use client"

import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { FlashcardCard } from "./FlashcardCard"
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
const POLL_TIMEOUT_MS = 120_000

interface SessionSummary {
  know: number
  unsure: number
  forgot: number
}

export function FlashcardPanel({ fileId, canFlashcard }: Props) {
  const [state, setState] = useState<PanelState>("idle")
  const [deckId, setDeckId] = useState<number | null>(null)
  const [cards, setCards] = useState<CardPublic[]>([])
  const [cardIndex, setCardIndex] = useState(0)
  const [cardCount, setCardCount] = useState<"10" | "20" | "30">("20")
  const [history, setHistory] = useState<DeckHistoryItem[]>([])
  const [boxCounts, setBoxCounts] = useState<Record<string, number> | null>(null)
  const [dueCount, setDueCount] = useState(0)
  const [openDeckId, setOpenDeckId] = useState<number | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [summary, setSummary] = useState<SessionSummary>({ know: 0, unsure: 0, forgot: 0 })

  const pollStartRef = useRef<number>(0)

  function refreshHistory() {
    getDeckHistory(fileId)
      .then((h) => {
        setHistory(h.items)
        setBoxCounts(h.box_counts ?? null)
        setOpenDeckId(h.has_open_deck ? (h.open_deck_id ?? null) : null)
      })
      .catch(() => {})
  }

  // On mount: load history and resume any open deck or start due-card session
  useEffect(() => {
    if (!canFlashcard) return
    getDeckHistory(fileId)
      .then((h) => {
        setHistory(h.items)
        setBoxCounts(h.box_counts ?? null)
        if (h.has_open_deck && h.open_deck_id != null) {
          setOpenDeckId(h.open_deck_id)
          resumeDeck(h.open_deck_id)
        } else {
          setOpenDeckId(null)
          getDueCards(fileId)
            .then((d) => setDueCount(d.total_due))
            .catch(() => {})
        }
      })
      .catch(() => {})
  }, [fileId, canFlashcard]) // eslint-disable-line react-hooks/exhaustive-deps

  async function resumeDeck(id: number) {
    setDeckId(id)
    try {
      const detail = await getDeck(id)
      if (detail.status === "ready" && detail.cards?.length) {
        setCards(detail.cards)
        setCardIndex(0)
        setSummary({ know: 0, unsure: 0, forgot: 0 })
        setState("reviewing")
      } else if (detail.status === "pending" || detail.status === "generating") {
        pollStartRef.current = Date.now()
        setState("generating")
      } else if (detail.status === "failed") {
        setErrorMsg(detail.error_msg ?? "Generation failed.")
        setState("error")
      }
    } catch {
      setState("idle")
    }
  }

  // Polling
  useEffect(() => {
    if (state !== "generating" || deckId == null) return
    const interval = setInterval(async () => {
      if (Date.now() - pollStartRef.current > POLL_TIMEOUT_MS) {
        clearInterval(interval)
        setErrorMsg("Deck generation timed out. Please try again.")
        setState("error")
        return
      }
      try {
        const detail = await getDeck(deckId)
        if (detail.status === "ready" && detail.cards?.length) {
          clearInterval(interval)
          setCards(detail.cards)
          setCardIndex(0)
          setSummary({ know: 0, unsure: 0, forgot: 0 })
          setState("reviewing")
          refreshHistory()
        } else if (detail.status === "failed") {
          clearInterval(interval)
          setErrorMsg(detail.error_msg ?? "Generation failed.")
          setState("error")
        }
      } catch {
        // transient — let loop retry
      }
    }, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [state, deckId]) // eslint-disable-line react-hooks/exhaustive-deps

  async function handleGenerate() {
    setErrorMsg(null)
    try {
      const res = await generateDeck(fileId, {
        card_count: Number(cardCount) as 10 | 20 | 30,
      })
      setDeckId(res.deck_id)
      pollStartRef.current = Date.now()
      setState("generating")
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail ?? "Failed to start deck generation.")
    }
  }

  async function handleStartDueReview() {
    try {
      const due = await getDueCards(fileId)
      if (due.cards.length === 0) return
      setCards(due.cards)
      setCardIndex(0)
      setSummary({ know: 0, unsure: 0, forgot: 0 })
      setDeckId(null)
      setState("reviewing")
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail ?? "Failed to load due cards.")
    }
  }

  async function handleReview(result: ReviewResult) {
    const card = cards[cardIndex]
    if (!card) return

    try {
      await reviewCard(card.id, result)
    } catch {
      // non-fatal — continue anyway
    }

    setSummary((prev) => ({ ...prev, [result]: prev[result] + 1 }))

    if (cardIndex + 1 >= cards.length) {
      setState("done")
      refreshHistory()
      getDueCards(fileId).then((d) => setDueCount(d.total_due)).catch(() => {})
    } else {
      setCardIndex((i) => i + 1)
    }
  }

  function handleBack() {
    setCardIndex((i) => Math.max(0, i - 1))
  }

  function handleForward() {
    setCardIndex((i) => Math.min(cards.length - 1, i + 1))
  }

  function handleReset() {
    setDeckId(null)
    setCards([])
    setCardIndex(0)
    setErrorMsg(null)
    setSummary({ know: 0, unsure: 0, forgot: 0 })
    setState("idle")
    refreshHistory()
    getDueCards(fileId).then((d) => setDueCount(d.total_due)).catch(() => {})
  }

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
    <div className="flex-1 flex flex-col min-h-0 gap-3 p-4">
      {errorMsg && (
        <Alert variant="destructive">
          <AlertDescription className="text-xs">{errorMsg}</AlertDescription>
        </Alert>
      )}

      {/* ── IDLE ── */}
      {state === "idle" && (
        <div className="space-y-4">
          {dueCount > 0 && (
            <Button variant="outline" onClick={handleStartDueReview} className="w-full">
              Review {dueCount} due card{dueCount !== 1 ? "s" : ""}
            </Button>
          )}
          <div className="flex items-end gap-3">
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground font-medium">Cards</p>
              <Select
                value={cardCount}
                onValueChange={(v) => setCardCount(v as "10" | "20" | "30")}
              >
                <SelectTrigger className="w-24 h-8 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="10">10</SelectItem>
                  <SelectItem value="20">20</SelectItem>
                  <SelectItem value="30">30</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button onClick={handleGenerate} className="flex-1">
              Generate flashcards
            </Button>
          </div>
          <FlashcardHistory items={history} boxCounts={boxCounts} />
        </div>
      )}

      {/* ── GENERATING ── */}
      {state === "generating" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-3">
          <div className="h-8 w-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
          <p className="text-sm text-muted-foreground">Generating flashcards…</p>
          <p className="text-sm text-muted-foreground">This may take up to a minute.</p>
        </div>
      )}

      {/* ── REVIEWING ── */}
      {state === "reviewing" && cards[cardIndex] && (
        <FlashcardCard
          card={cards[cardIndex]}
          index={cardIndex}
          total={cards.length}
          onReview={handleReview}
          onPrev={handleBack}
          onNext={handleForward}
        />
      )}

      {/* ── DONE ── */}
      {state === "done" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-4 py-4">
          <p className="text-base font-medium text-foreground">Session complete!</p>
          <div className="grid grid-cols-3 gap-3 text-center text-sm w-full max-w-xs">
            <div className="rounded-lg border border-emerald-400/40 bg-emerald-50 dark:bg-emerald-950/30 p-3">
              <p className="text-xl font-bold text-emerald-600">{summary.know}</p>
              <p className="text-xs text-muted-foreground">Know</p>
            </div>
            <div className="rounded-lg border border-amber-400/40 bg-amber-50 dark:bg-amber-950/30 p-3">
              <p className="text-xl font-bold text-amber-600">{summary.unsure}</p>
              <p className="text-xs text-muted-foreground">Unsure</p>
            </div>
            <div className="rounded-lg border border-red-400/40 bg-red-50 dark:bg-red-950/30 p-3">
              <p className="text-xl font-bold text-red-600">{summary.forgot}</p>
              <p className="text-xs text-muted-foreground">Forgot</p>
            </div>
          </div>
          {dueCount > 0 && (
            <Button variant="outline" size="sm" onClick={handleStartDueReview}>
              Review {dueCount} due card{dueCount !== 1 ? "s" : ""}
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={handleReset}>
            Generate new deck
          </Button>
        </div>
      )}

      {/* ── ERROR ── */}
      {state === "error" && (
        <div className="flex flex-col items-center gap-3 pt-4">
          <Button variant="outline" onClick={handleReset}>
            Back to setup
          </Button>
        </div>
      )}
    </div>
  )
}
