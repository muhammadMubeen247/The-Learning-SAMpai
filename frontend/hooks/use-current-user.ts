"use client"

import { useEffect, useState } from "react"
import API from "@/api/axios"

export type CurrentUser = {
  id: number
  username: string
  email: string
}

export function useCurrentUser() {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const stored = typeof window !== "undefined" ? localStorage.getItem("user") : null
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as CurrentUser
        setUser(parsed)
        setLoading(false)
        return
      } catch {
        // fall through to API fetch
      }
    }

    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null
    if (!token) {
      setLoading(false)
      return
    }

    ;(async () => {
      try {
        const res = await API.get("/auth/me")
        const me: CurrentUser = {
          id: res.data.id,
          username: res.data.username,
          email: res.data.email,
        }
        setUser(me)
        if (typeof window !== "undefined") {
          localStorage.setItem("user", JSON.stringify(me))
        }
      } catch {
        // invalid token or other error, treat as logged out
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  return { user, loading, setUser }
}


