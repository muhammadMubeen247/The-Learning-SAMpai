"use client"

import { type DeckHistoryItem } from "@/api/flashcards"

const BOX_COLORS = [
  "bg-red-400",
  "bg-orange-400",
  "bg-yellow-400",
  "bg-blue-400",
  "bg-emerald-400",
]

interface Props {
  items: DeckHistoryItem[]
  boxCounts?: Record<string, number> | null
}

export function FlashcardHistory({ items, boxCounts }: Props) {
  if (items.length === 0) {
    return <p className="text-xs text-muted-foreground text-center py-4">No flashcard decks yet.</p>
  }

  const totalCards = boxCounts
    ? Object.values(boxCounts).reduce((a, b) => a + b, 0)
    : 0

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground font-medium">Past decks</p>

      {boxCounts && totalCards > 0 && (
        <div className="space-y-1">
          <p className="text-[11px] text-muted-foreground">Mastery progress (latest deck)</p>
          <div className="flex h-2 rounded-full overflow-hidden gap-px">
            {[1, 2, 3, 4, 5].map((box) => {
              const count = boxCounts[String(box)] ?? 0
              const pct = totalCards > 0 ? (count / totalCards) * 100 : 0
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
          <div className="flex justify-between text-[10px] text-muted-foreground/60">
            <span>Learning</span>
            <span>Mastered</span>
          </div>
        </div>
      )}

      <div className="space-y-1.5">
        {items.slice(0, 5).map((item) => (
          <div
            key={item.deck_id}
            className="flex items-center justify-between rounded-lg border border-border/50 bg-card/30 px-3 py-2 text-xs"
          >
            <div>
              <span className="font-medium text-foreground">
                {item.card_count != null ? `${item.card_count} cards` : "—"}
              </span>
              <span className="text-muted-foreground ml-2">
                {new Date(item.created_at).toLocaleDateString()}
              </span>
            </div>
            <span className={`capitalize text-[11px] ${
              item.status === "ready"
                ? "text-emerald-600"
                : item.status === "failed"
                ? "text-destructive"
                : "text-muted-foreground"
            }`}>
              {item.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
