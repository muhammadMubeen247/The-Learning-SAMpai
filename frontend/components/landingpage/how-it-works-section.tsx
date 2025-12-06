"use client"

import dynamic from "next/dynamic"
import { motion } from "motion/react"
import { useInView } from "motion/react"
import { useRef, useMemo } from "react"
import { Database, Brain, Sparkles, TrendingUp } from "lucide-react"
import { useTheme } from "@/hooks/use-theme"

const Aurora = dynamic(() => import("@/components/backgrounds/Aurora"), { ssr: false })
const MagicBento = dynamic(() => import("@/components/backgrounds/magic-bento"), { ssr: false })

export function HowItWorksSection() {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: "-100px" })
  const { theme } = useTheme()
  const isDark = theme === "dark"

  const auroraStops = useMemo(
    () =>
      theme === "dark"
        ? ["#0EA5E9", "#2563EB", "#06B6D4"] // cyan → blue → teal (darker energy)
        : ["#38BDF8", "#60A5FA", "#22D3EE"], // softer blue/cyan for light
    [theme],
  )

  const howItWorksItems = useMemo(
    () => [
      {
        color: "#030712", // background for card surface
        title: "RAG Retrieval",
        description: "Fetch the most relevant passages from the knowledge base in real time.",
        label: "Step 1",
        icon: Database,
      },
      {
        color: "#030712",
        title: "Understand Context",
        description: "Infer student intent and level to tailor the next response.",
        label: "Step 2",
        icon: Brain,
      },
      {
        color: "#030712",
        title: "Generate Response",
        description: "Compose explanations, diagrams, or quizzes grounded in retrieved knowledge.",
        label: "Step 3",
        icon: Sparkles,
      },
      {
        color: "#030712",
        title: "Feedback Loop",
        description: "Measure outcomes and adapt future content for continuous improvement.",
        label: "Step 4",
        icon: TrendingUp,
      },
    ],
    [],
  )

  return (
    <section id="how-it-works" ref={ref} className="relative overflow-hidden">
      <div className="pointer-events-none absolute inset-x-0 top-0" aria-hidden="true">
        <div className="h-48 sm:h-56 md:h-72 lg:h-80 w-screen">
          <Aurora key={theme} colorStops={auroraStops} amplitude={1.0} blend={0.55} speed={0.85} />
        </div>
        <div className="absolute inset-x-0 -bottom-1 h-16 bg-gradient-to-b from-transparent to-background" />
      </div>

      <div className="relative pt-20 sm:pt-24 md:pt-28 lg:pt-32 pb-16 sm:pb-24 bg-muted/30">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={isInView ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.8 }}
            className="text-center mb-10 sm:mb-14"
          >
            <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold mb-6 text-balance">
              How It{" "}
              <span className="bg-gradient-to-r from-chart-1 to-chart-2 bg-clip-text text-transparent">Works</span>
            </h2>
            <p className="text-lg sm:text-xl text-muted-foreground max-w-3xl mx-auto leading-relaxed text-pretty">
              Powered by advanced RAG technology and machine learning
            </p>
          </motion.div>

          <div className="flex justify-center">
            <MagicBento
              key={theme}
              items={howItWorksItems}
              textAutoHide={true}
              enableStars={true}
              enableSpotlight={true}
              enableBorderGlow={true}
              enableTilt={false}
              enableMagnetism={true}
              clickEffect={true}
              glowColor={isDark ? "14, 165, 233" : "56, 189, 248"}
              spotlightRadius={300}
              particleCount={12}
              disableAnimations={false}
              isDark={isDark}
            />
          </div>
        </div>
      </div>
    </section>
  )
}
