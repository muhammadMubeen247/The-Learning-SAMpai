import API from "@/api/axios"

export type DeckStatus = "pending" | "generating" | "ready" | "failed"
export type CardType = "definition" | "concept" | "example" | "formula"
export type ReviewResult = "know" | "unsure" | "forgot"

export interface CardPublic {
  id: number
  front: string
  back: string
  card_type: CardType
  box: number
  next_review_at: string
}

export interface DeckDetail {
  deck_id: number
  status: DeckStatus
  card_count?: number | null
  created_at: string
  ready_at?: string | null
  error_msg?: string | null
  cards?: CardPublic[] | null
}

export interface DueCardsResponse {
  cards: CardPublic[]
  total_due: number
}

export interface ReviewResponse {
  card_id: number
  box: number
  next_review_at: string
}

export interface DeckHistoryItem {
  deck_id: number
  status: DeckStatus
  card_count?: number | null
  created_at: string
  ready_at?: string | null
}

export interface DeckHistoryResponse {
  items: DeckHistoryItem[]
  box_counts?: Record<string, number> | null
  has_open_deck: boolean
  open_deck_id?: number | null
}

export async function generateDeck(
  fileId: number,
  body: { card_count: 10 | 20 | 30 }
): Promise<{ deck_id: number; status: DeckStatus }> {
  const res = await API.post(`/flashcards/files/${fileId}/generate`, body)
  return res.data
}

export async function getDeck(deckId: number): Promise<DeckDetail> {
  const res = await API.get(`/flashcards/${deckId}`)
  return res.data
}

export async function getDueCards(fileId: number): Promise<DueCardsResponse> {
  const res = await API.get(`/flashcards/files/${fileId}/due`)
  return res.data
}

export async function reviewCard(
  cardId: number,
  result: ReviewResult
): Promise<ReviewResponse> {
  const res = await API.post(`/flashcards/cards/${cardId}/review`, { result })
  return res.data
}

export async function getDeckHistory(fileId: number): Promise<DeckHistoryResponse> {
  const res = await API.get(`/flashcards/files/${fileId}/history`)
  return res.data
}
