"use client"

import dynamic from "next/dynamic"
import { motion } from "motion/react"
import { AlertCircle, TrendingDown, Clock } from "lucide-react"
import { useInView } from "motion/react"
import { useRef } from "react"
import { useTheme } from "@/hooks/use-theme"

const PixelBlast = dynamic(() => import("@/components/backgrounds/pixel-blast"), { ssr: false })
const ElectricBorder = dynamic(() => import("@/components/backgrounds/electric-border"), { ssr: false })

export function ProblemSection() {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: "-100px" })
  const { theme, mounted } = useTheme()

  const problems = [
    {
      icon: AlertCircle,
      title: "One-Size-Fits-All",
      description: "Students lose motivation due to lack of personalization",
    },
    {
      icon: Clock,
      title: "Administrative Overload",
      description: "Teachers face hours of grading and manual tracking",
    },
    {
      icon: TrendingDown,
      title: "Passive Learning",
      description: "80% of students quit online courses before completion",
    },
  ]

  const pixelColor = theme === "dark" ? "#7c3aed" : "#6366f1"
  const borderColor = theme === "dark" ? "#7c3aed" : "#6366f1"

  if (!mounted) {
    return (
      <section ref={ref} className="relative py-20 sm:py-32 overflow-hidden">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold mb-6 text-balance">
              The Problem with <span className="text-muted-foreground line-through">Traditional</span> Learning
            </h2>
            <p className="text-lg sm:text-xl text-muted-foreground max-w-3xl mx-auto leading-relaxed text-pretty">
              Current online learning platforms treat every student the same. They follow a fixed sequence of lessons,
              give generic feedback, and often fail to adapt.
            </p>
          </div>
        </div>
      </section>
    )
  }

  return (
    <section ref={ref} className="relative py-20 sm:py-32 overflow-hidden">
      <div className="absolute inset-0 opacity-30">
        <PixelBlast
          variant="circle"
          pixelSize={4}
          color={pixelColor}
          patternScale={2.5}
          patternDensity={1.1}
          pixelSizeJitter={0.4}
          enableRipples
          rippleSpeed={0.35}
          rippleThickness={0.15}
          rippleIntensityScale={1.2}
          liquid
          liquidStrength={0.08}
          liquidRadius={1}
          liquidWobbleSpeed={4}
          speed={0.5}
          edgeFade={0.4}
          transparent
        />
      </div>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.8 }}
          className="text-center mb-16"
        >
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold mb-6 text-balance">
            The Problem with <span className="text-muted-foreground line-through">Traditional</span> Learning
          </h2>
          <p className="text-lg sm:text-xl text-muted-foreground max-w-3xl mx-auto leading-relaxed text-pretty">
            Current online learning platforms treat every student the same. They follow a fixed sequence of lessons,
            give generic feedback, and often fail to adapt.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 lg:gap-8 max-w-6xl mx-auto">
          {problems.map((problem, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 30 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.6, delay: index * 0.1 }}
              className="relative group"
            >
              <ElectricBorder
                color={borderColor}
                speed={1.2}
                chaos={0.8}
                thickness={2}
                style={{ borderRadius: "1rem" }}
              >
                <div className="relative p-8 rounded-2xl bg-card/80 backdrop-blur-sm h-full">
                  <div className="w-12 h-12 rounded-xl bg-destructive/10 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-300">
                    <problem.icon className="w-6 h-6 text-destructive" />
                  </div>
                  <h3 className="text-xl font-semibold mb-3">{problem.title}</h3>
                  <p className="text-muted-foreground leading-relaxed">{problem.description}</p>
                </div>
              </ElectricBorder>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
