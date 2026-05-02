"use client"

import { createContext, useContext, useEffect, useState, type ReactNode } from "react"
import { ThemeProvider } from "next-themes"
import { Toaster } from "@/components/ui/sonner"
import { RealtimeProvider } from "@/providers/realtime-provider"

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
        <RealtimeProvider>
          {children}
        </RealtimeProvider>
        <Toaster />
      </ThemeProvider>
    </AuthContext.Provider>
  )
}
