"use client"

import { motion, useMotionValue, useTransform } from "motion/react"
import { useState } from "react"
import type React from "react"

type StackCard =
  | { id: number | string; img: string }
  | {
      id: number | string
      title?: string
      subtitle?: string
      details?: string
      icon?: React.ComponentType<{ className?: string }>
      img?: string
    }

function CardRotate({ children, onSendToBack, sensitivity }) {
  const x = useMotionValue(0)
  const y = useMotionValue(0)
  const rotateX = useTransform(y, [-100, 100], [60, -60])
  const rotateY = useTransform(x, [-100, 100], [-60, 60])

  function handleDragEnd(_, info) {
    if (Math.abs(info.offset.x) > sensitivity || Math.abs(info.offset.y) > sensitivity) {
      onSendToBack()
    } else {
      x.set(0)
      y.set(0)
    }
  }

  return (
    <motion.div
      className="absolute cursor-grab"
      style={{ x, y, rotateX, rotateY }}
      drag
      dragConstraints={{ top: 0, right: 0, bottom: 0, left: 0 }}
      dragElastic={0.6}
      whileTap={{ cursor: "grabbing" }}
      onDragEnd={handleDragEnd}
    >
      {children}
    </motion.div>
  )
}

export default function Stack({
  randomRotation = false,
  sensitivity = 200,
  cardDimensions = { width: 208, height: 208 },
  cardsData = [],
  animationConfig = { stiffness: 260, damping: 20 },
  sendToBackOnClick = false,
  onCardClick,
  expandable = false,
  bringToFrontOnExpand = true,
  expandedId: controlledExpandedId,
  onExpandedChange,
  contentVariant = "default",
}: {
  randomRotation?: boolean
  sensitivity?: number
  cardDimensions?: { width: number; height: number }
  cardsData?: StackCard[]
  animationConfig?: { stiffness: number; damping: number }
  sendToBackOnClick?: boolean
  onCardClick?: (card: StackCard) => void
  expandable?: boolean
  bringToFrontOnExpand?: boolean
  expandedId?: number | string | null
  onExpandedChange?: (id: number | string | null) => void
  contentVariant?: "default" | "teacher"
}) {
  const [cards, setCards] = useState(
    cardsData.length
      ? cardsData
      : [
          { id: 1, img: "https://images.unsplash.com/photo-1480074568708-e7b720bb3f09?q=80&w=500&auto=format" },
          { id: 2, img: "https://images.unsplash.com/photo-1449844908441-8829872d2607?q=80&w=500&auto=format" },
          { id: 3, img: "https://images.unsplash.com/photo-1452626212852-811d58933cae?q=80&w=500&auto=format" },
          { id: 4, img: "https://images.unsplash.com/photo-1572120360610-d971b9d7767c?q=80&w=500&auto=format" },
        ],
  )
  const [expanded, setExpanded] = useState<number | string | null>(null)
  const isExpanded = (id: number | string) => (controlledExpandedId ?? expanded) === id

  const sendToBack = (id) => {
    setCards((prev) => {
      const newCards = [...prev]
      const index = newCards.findIndex((card) => card.id === id)
      const [card] = newCards.splice(index, 1)
      newCards.unshift(card)
      return newCards
    })
  }

  const bringToFront = (id) => {
    setCards((prev) => {
      const newCards = [...prev]
      const index = newCards.findIndex((card) => card.id === id)
      const [card] = newCards.splice(index, 1)
      newCards.push(card)
      return newCards
    })
  }

  return (
    <div className="relative" style={{ width: cardDimensions.width, height: cardDimensions.height, perspective: 600 }}>
      {cards.map((card, index) => {
        const randomRotate = randomRotation ? Math.random() * 10 - 5 : 0
        const isImage = "img" in card && card.img

        return (
          <CardRotate key={card.id} onSendToBack={() => sendToBack(card.id)} sensitivity={sensitivity}>
            <motion.div
              className="rounded-2xl overflow-hidden border border-border bg-card/80 backdrop-blur-xl relative shadow-2xl"
              onClick={() => {
                if (expandable) {
                  const currentlyExpanded = isExpanded(card.id)
                  if (currentlyExpanded) {
                    // collapse, keep card on top
                    onExpandedChange ? onExpandedChange(null) : setExpanded(null)
                  } else {
                    if (bringToFrontOnExpand) bringToFront(card.id)
                    onExpandedChange ? onExpandedChange(card.id) : setExpanded(card.id)
                  }
                } else if (sendToBackOnClick) {
                  sendToBack(card.id)
                }
                if (onCardClick) onCardClick(card)
              }}
              animate={{
                rotateZ: isExpanded(card.id) ? 0 : (cards.length - index - 1) * 4 + randomRotate,
                scale: isExpanded(card.id) ? 1.12 : 1 + index * 0.06 - cards.length * 0.06,
                transformOrigin: isExpanded(card.id) ? "50% 60%" : "90% 90%",
              }}
              initial={false}
              transition={{ type: "spring", stiffness: animationConfig.stiffness, damping: animationConfig.damping }}
              style={{
                width: isExpanded(card.id) ? cardDimensions.width + 80 : cardDimensions.width,
                height: isExpanded(card.id) ? cardDimensions.height + 60 : cardDimensions.height,
              }}
            >
              <div
                className={`pointer-events-none absolute inset-0 rounded-2xl -z-10 blur-xl bg-gradient-to-br from-chart-1/20 to-chart-2/20 ${
                  isExpanded(card.id) ? "opacity-100" : "opacity-70"
                }`}
              />
              {isImage ? (
                <img
                  src={(card as any).img || "/placeholder.svg"}
                  alt={`card-${card.id}`}
                  className="w-full h-full object-cover pointer-events-none"
                />
              ) : (
                <div
                  className={
                    contentVariant === "teacher"
                      ? "w-full h-full p-5 flex flex-col justify-between"
                      : "w-full h-full p-4 flex flex-col justify-between"
                  }
                >
                  <div className={contentVariant === "teacher" ? "flex items-start gap-4" : "flex items-start gap-3"}>
                    {"icon" in card && card.icon ? (
                      <card.icon
                        className={
                          contentVariant === "teacher" ? "w-10 h-10 text-chart-1 flex-shrink-0" : "w-6 h-6 text-chart-1"
                        }
                      />
                    ) : null}
                    <div className="min-w-0">
                      <h4
                        className={
                          contentVariant === "teacher"
                            ? "font-semibold text-xl leading-tight truncate"
                            : "font-semibold text-base"
                        }
                      >
                        {("title" in card && card.title) || "Tool"}
                      </h4>
                      <p
                        className={
                          contentVariant === "teacher"
                            ? "text-sm text-muted-foreground leading-snug"
                            : "text-xs text-muted-foreground"
                        }
                      >
                        {("subtitle" in card && card.subtitle) || "Interactive AI-powered tool"}
                      </p>
                    </div>
                  </div>

                  <p
                    className={
                      contentVariant === "teacher"
                        ? "text-sm text-muted-foreground mt-3 leading-relaxed line-clamp-4"
                        : "text-xs text-muted-foreground mt-2 line-clamp-3"
                    }
                  >
                    {("details" in card && card.details) || "Tap to learn more"}
                  </p>

                  {contentVariant === "teacher" ? (
                    <div className="flex items-center gap-2 mt-3">
                      <span className="text-xs px-2 py-1 rounded-full bg-primary/10 text-primary">AI-assisted</span>
                      <span className="text-xs px-2 py-1 rounded-full bg-muted text-muted-foreground">
                        Teacher tool
                      </span>
                    </div>
                  ) : null}
                </div>
              )}
            </motion.div>
          </CardRotate>
        )
      })}
    </div>
  )
}
