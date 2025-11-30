"use client"

import type React from "react"
import { AuthCard } from "@/components/signup-login/auth-card"
import Threads from "@/components/backgrounds/threads"
import { useTheme } from "@/hooks/use-theme"

export default function LoginPage(): React.ReactNode {
  const { theme } = useTheme()
  return (
    <main className="relative min-h-[100dvh] w-full overflow-hidden flex items-center justify-center px-4">
            {/* Animated Background */}
      <div className="absolute inset-0 z-0">
        <Threads key={theme} color={[0.3, 0.6, 1]} amplitude={1.2} distance={0.3} enableMouseInteraction={true} />
      </div>
      {/* Soft scene lighting */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -z-20"
        style={{
          background:
            "radial-gradient(60% 50% at 50% 10%, color-mix(in oklch, var(--color-chart-2) 16%, transparent) 0%, transparent 60%), radial-gradient(40% 40% at 80% 85%, color-mix(in oklch, var(--color-chart-1) 14%, transparent) 0%, transparent 70%)",
        }}
      />
      <AuthCard initialMode="login" />
    </main>
  )
}
