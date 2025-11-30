"use client"

import { motion } from "motion/react"
import { useInView } from "motion/react"
import { useRef } from "react"
import { Brain, Zap, Target, TrendingUp } from "lucide-react"
import LightRays from "@/components/backgrounds/light-rays"
import OrbEnhanced from "@/components/backgrounds/orb-enhanced"
import { useTheme } from "@/hooks/use-theme"

export function SolutionSection() {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: "-100px" })
  const { theme, mounted } = useTheme()

  const features = [
    {
      icon: Brain,
      title: "Monitors Progress",
      description: "Continuously tracks each learner's journey",
      hue: 260,
    },
    {
      icon: Zap,
      title: "Real-Time Adaptation",
      description: "Adjusts curriculum dynamically",
      hue: 220,
    },
    {
      icon: Target,
      title: "Personalized Explanations",
      description: "Provides tailored hints and guidance",
      hue: 280,
    },
    {
      icon: TrendingUp,
      title: "Teacher Support",
      description: "Automates content creation and analytics",
      hue: 200,
    },
  ]

  const raysColor = theme === "dark" ? "#8b5cf6" : "#6366f1"

  if (!mounted) {
    return (
      <section ref={ref} className="relative py-20 sm:py-32 overflow-hidden">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold mb-6 text-balance">
              Our{" "}
              <span className="bg-gradient-to-r from-chart-1 to-chart-2 bg-clip-text text-transparent">AI-Powered</span>{" "}
              Solution
            </h2>
            <p className="text-lg sm:text-xl text-muted-foreground max-w-3xl mx-auto leading-relaxed text-pretty">
              The Learning SAMpai transforms education into a dynamic, adaptive experience using AI, RAG, and
              data-driven learning intelligence.
            </p>
          </div>
        </div>
      </section>
    )
  }

  return (
    <section ref={ref} className="relative py-20 sm:py-32 overflow-hidden">
      <div className="absolute inset-0 opacity-40 dark:opacity-50">
        <LightRays
          key={theme}
          raysOrigin="top-center"
          raysColor={raysColor}
          raysSpeed={0.6}
          lightSpread={2.5}
          rayLength={2}
          pulsating={true}
          fadeDistance={0.7}
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
            Our{" "}
            <span className="bg-gradient-to-r from-chart-1 to-chart-2 bg-clip-text text-transparent">AI-Powered</span>{" "}
            Solution
          </h2>
          <p className="text-lg sm:text-xl text-muted-foreground max-w-3xl mx-auto leading-relaxed text-pretty">
            The Learning SAMpai transforms education into a dynamic, adaptive experience using AI, RAG, and data-driven
            learning intelligence.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8 max-w-7xl mx-auto">
          {features.map((feature, index) => (
            <motion.div
              key={`${theme}-${index}`}
              initial={{ opacity: 0, scale: 0.9 }}
              animate={isInView ? { opacity: 1, scale: 1 } : {}}
              transition={{ duration: 0.5, delay: index * 0.1 }}
              className="relative group"
            >
              <div className="relative h-[280px] rounded-2xl overflow-hidden">
                <div className="absolute inset-0">
                  <OrbEnhanced
                    key={theme}
                    hue={feature.hue}
                    hoverIntensity={0.4}
                    rotateOnHover={true}
                    forceHoverState={false}
                  />
                </div>

                <div className="absolute inset-0 flex flex-col items-center justify-center p-6 bg-gradient-to-b from-transparent via-background/20 to-background/60 backdrop-blur-[2px] group-hover:backdrop-blur-[1px] transition-all duration-300">
                  <div className="w-14 h-14 rounded-xl bg-background/80 backdrop-blur-sm flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-300 shadow-lg">
                    <feature.icon className="w-7 h-7 text-chart-1" />
                  </div>
                  <h3 className="text-lg font-semibold mb-2 text-center text-foreground drop-shadow-lg">
                    {feature.title}
                  </h3>
                  <p className="text-sm text-foreground/90 leading-relaxed text-center drop-shadow-md">
                    {feature.description}
                  </p>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
