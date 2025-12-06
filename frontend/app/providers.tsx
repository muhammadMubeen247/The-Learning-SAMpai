"use client"

import { createContext, useContext, useEffect, useState, type ReactNode } from "react"
import { ThemeProvider } from "next-themes"

type AuthContextType = {
  isHydrated: boolean
}

const AuthContext = createContext<AuthContextType>({ isHydrated: false })

export function useAuthContext() {
  return useContext(AuthContext)
}

export function Providers({ children }: { children: ReactNode }) {
  const [isHydrated, setIsHydrated] = useState(false)

  useEffect(() => {
    setIsHydrated(true)
  }, [])

  return (
    <AuthContext.Provider value={{ isHydrated }}>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
        {children}
      </ThemeProvider>
    </AuthContext.Provider>
  )
}
