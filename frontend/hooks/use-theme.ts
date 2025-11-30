"use client"

import { useEffect, useState } from "react"

export function useTheme() {
  const [theme, setTheme] = useState<"light" | "dark">("dark")
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
    const savedTheme = localStorage.getItem("theme") as "light" | "dark" | null
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches
    const initialTheme = savedTheme || (prefersDark ? "dark" : "light")
    setTheme(initialTheme)

    // Ensure the document has the correct class immediately after mount
    document.documentElement.classList.toggle("dark", initialTheme === "dark")
    document.documentElement.setAttribute("data-theme", initialTheme)
    // Notify listeners
    window.dispatchEvent(new Event("themechange"))

    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === "theme" && e.newValue) {
        const nextTheme = e.newValue as "light" | "dark"
        setTheme(nextTheme)
        document.documentElement.classList.toggle("dark", nextTheme === "dark")
        document.documentElement.setAttribute("data-theme", nextTheme)
        window.dispatchEvent(new Event("themechange"))
      }
    }

    const handleThemeChange = () => {
      const currentTheme = localStorage.getItem("theme") as "light" | "dark" | null
      if (currentTheme) {
        setTheme(currentTheme)
        document.documentElement.classList.toggle("dark", currentTheme === "dark")
        document.documentElement.setAttribute("data-theme", currentTheme)
      }
    }

    window.addEventListener("storage", handleStorageChange)
    window.addEventListener("themechange", handleThemeChange)

    return () => {
      window.removeEventListener("storage", handleStorageChange)
      window.removeEventListener("themechange", handleThemeChange)
    }
  }, [])

  return { theme, mounted }
}
