"use client"

import { useRouter as useNextRouter } from "next/navigation"
import { useCallback } from "react"

/**
 * Custom hook that wraps Next.js router to trigger loading state
 * on navigation. Use this instead of useRouter when you want
 * the loading orb to appear immediately.
 */
export function useNavigation() {
  const router = useNextRouter()

  const push = useCallback((href: string) => {
    // Dispatch custom event to trigger loading
    window.dispatchEvent(new CustomEvent('navigation-start'))
    router.push(href)
  }, [router])

  const replace = useCallback((href: string) => {
    // Dispatch custom event to trigger loading
    window.dispatchEvent(new CustomEvent('navigation-start'))
    router.replace(href)
  }, [router])

  return {
    ...router,
    push,
    replace,
  }
}

