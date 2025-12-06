"use client"

import { useEffect, useState } from "react"
import { useAuthContext } from "@/app/providers"
import API from "@/api/axios"

export type CurrentUser = {
  id: number
  username: string
  email: string
}

export function useCurrentUser() {
  const { isHydrated } = useAuthContext()
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!isHydrated) return

    const stored = localStorage.getItem("user")
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

    const token = localStorage.getItem("token")
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
        localStorage.setItem("user", JSON.stringify(me))
      } catch {
        // invalid token or other error, treat as logged out
        localStorage.removeItem("token")
        localStorage.removeItem("user")
      } finally {
        setLoading(false)
      }
    })()
  }, [isHydrated])

  return { user, loading: loading || !isHydrated, setUser }
}


