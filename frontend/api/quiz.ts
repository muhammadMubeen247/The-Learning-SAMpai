import API from "@/api/axios"

export type Difficulty = "easy" | "medium" | "hard"
export type QuizStatus = "pending" | "generating" | "ready" | "failed" | "submitted"
export type QuestionType = "mcq" | "tf"

export interface QuestionPublic {
  id: number
  type: QuestionType
  prompt: string
  options?: string[]
}

export interface AnswerReview {
  question_id: number
  type: QuestionType
  prompt: string
  options?: string[]
  user_answer?: number | boolean | null
  correct_answer: number | boolean
  correct: boolean
  explanation: string
}

export interface AttemptResult {
  attempt_id: number
  quiz_id: number
  score: number
  correct_count: number
  total_count: number
  submitted_at: string
  review: AnswerReview[]
}

export interface QuizDetail {
  quiz_id: number
  status: QuizStatus
  difficulty: Difficulty
  difficulty_source: string
  num_questions: number
  created_at: string
  ready_at?: string | null
  questions?: QuestionPublic[] | null
  attempt?: AttemptResult | null
  error_msg?: string | null
}

export interface QuizHistoryItem {
  quiz_id: number
  difficulty: Difficulty
  num_questions: number
  score?: number | null
  correct_count?: number | null
  submitted_at?: string | null
  created_at: string
  status: QuizStatus
}

export interface QuizHistoryResponse {
  items: QuizHistoryItem[]
  has_open_quiz: boolean
  open_quiz_id?: number | null
}

export async function generateQuiz(
  fileId: number,
  body: { num_questions: 5 | 10 | 15; difficulty?: Difficulty }
): Promise<{ quiz_id: number; status: QuizStatus }> {
  const res = await API.post(`/quiz/files/${fileId}/generate`, body)
  return res.data
}

export async function getQuiz(quizId: number): Promise<QuizDetail> {
  const res = await API.get(`/quiz/${quizId}`)
  return res.data
}

export async function submitQuiz(
  quizId: number,
  answers: { question_id: number; answer: number | boolean }[]
): Promise<AttemptResult> {
  const res = await API.post(`/quiz/${quizId}/submit`, { answers })
  return res.data
}

export async function getQuizHistory(fileId: number): Promise<QuizHistoryResponse> {
  const res = await API.get(`/quiz/files/${fileId}/history`)
  return res.data
}
