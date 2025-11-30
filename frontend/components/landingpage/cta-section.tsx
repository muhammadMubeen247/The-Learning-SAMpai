"use client"

import { motion } from "framer-motion"
import { useInView } from "framer-motion"
import { useRef } from "react"
import { Button } from "@/components/ui/button"
import { ArrowRight, Sparkles } from "lucide-react"
import DotGrid from "@/components/backgrounds/dot-grid"
import { useTheme } from "@/hooks/use-theme"
import { useRouter } from "next/navigation"

export function CTASection() {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: "-100px" })
  const { theme, mounted } = useTheme()
  const router = useRouter()
  const resolvedTheme = mounted ? theme : "dark"
  const baseColor = resolvedTheme === "dark" ? "#3b82f6" /* blue-500 */ : "#2563eb" /* blue-600 */
  const activeColor = resolvedTheme === "dark" ? "#60a5fa" /* blue-400 */ : "#0ea5e9" /* cyan-500 */

  return (
    <section id="cta" ref={ref} className="relative py-20 sm:py-32 overflow-hidden">
      <div className="absolute inset-0">
        <DotGrid
          className="absolute inset-0 p-0 pointer-events-none opacity-35"
          dotSize={10}
          gap={18}
          baseColor={baseColor}
          activeColor={activeColor}
          proximity={120}
          shockRadius={220}
          shockStrength={4}
          resistance={700}
          returnDuration={1.4}
        />
        <div className="absolute inset-0 bg-gradient-to-b from-background/40 via-background/20 to-background/60 pointer-events-none" />
      </div>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.8 }}
          className="max-w-4xl mx-auto text-center"
        >
          <div className="inline-flex items-center space-x-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20 mb-8">
            <Sparkles className="w-4 h-4 text-chart-1" />
            <span className="text-sm font-medium">Join the Future of Learning</span>
          </div>

          <h2 className="text-3xl sm:text-4xl md:text-5xl lg:text-6xl font-bold mb-6 leading-tight text-balance">
            Learn. Grow. Evolve —{" "}
            <span className="bg-gradient-to-r from-chart-1 to-chart-2 bg-clip-text text-transparent">
              with The Learning SAMpai
            </span>
          </h2>

          <p className="text-lg sm:text-xl text-muted-foreground mb-10 max-w-2xl mx-auto leading-relaxed text-pretty">
            Because it's not just another LMS — it's a living, learning system that evolves with every student and
            teacher.
          </p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={isInView ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.8, delay: 0.2 }}
            className="flex flex-col sm:flex-row items-center justify-center gap-4"
          >
            <Button
              size="lg"
              className="text-base px-8 py-6 cursor-pointer bg-gradient-to-r from-chart-1 to-chart-2 hover:opacity-90 transition-all duration-300 group"
              onClick={() => router.push("/signup")}
            >
              Start Learning Today
              <ArrowRight className="ml-2 h-5 w-5 group-hover:translate-x-1 transition-transform" />
            </Button>
            <Button
              size="lg"
              variant="outline"
              className="text-base px-8 py-6 cursor-pointer border-2 hover:bg-accent transition-all duration-300 bg-transparent"
              onClick={() => router.push("/signup")}
            >
              Schedule a Demo
            </Button>
          </motion.div>
        </motion.div>
      </div>
    </section>
  )
}
