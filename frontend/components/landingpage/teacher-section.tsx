"use client"

import { motion } from "framer-motion"
import { useInView } from "react-intersection-observer"
import { useRef, useState, useEffect } from "react"
import { FileEdit, CheckCircle, BarChart3, Lightbulb, Palette, Shield, MessageCircle } from "lucide-react"
import Stack from "@/components/backgrounds/stack"
import Plasma from "@/components/backgrounds/plasma"
import { useTheme } from "@/hooks/use-theme"

export function TeacherSection() {
  const ref = useRef(null)
  const [inView, setInView] = useInView({ once: true, margin: "-100px" })
  const { theme } = useTheme()
  const [cardDims, setCardDims] = useState<{ width: number; height: number }>({ width: 480, height: 300 })

  useEffect(() => {
    const update = () => {
      const w = typeof window !== "undefined" ? window.innerWidth : 1024
      if (w < 380) setCardDims({ width: 300, height: 200 })
      else if (w < 640) setCardDims({ width: 340, height: 220 })
      else if (w < 768) setCardDims({ width: 400, height: 260 })
      else setCardDims({ width: 480, height: 300 })
    }
    update()
    window.addEventListener("resize", update)
    return () => window.removeEventListener("resize", update)
  }, [])

  const teacherCards = [
    {
      id: 1,
      title: "AI-Assisted Content Authoring",
      subtitle: "Summaries, quizzes, flashcards",
      details:
        "Upload lesson material. SAMpai drafts summaries, quizzes, flashcards, diagrams, and tailored examples aligned to your syllabus. Expand to see workflow tips and best practices.",
      icon: FileEdit,
    },
    {
      id: 2,
      title: "Automated Grading & Feedback",
      subtitle: "Instant and in-depth",
      details:
        "Objective items graded instantly. Essays receive rubric-based feedback, highlights, and correction suggestions. Expand for configurable rubrics and feedback tone.",
      icon: CheckCircle,
    },
    {
      id: 3,
      title: "Student Analytics Dashboard",
      subtitle: "Heatmaps & trends",
      details:
        "Spot struggling topics early via mastery trends, cohort comparisons, and prediction signals. Expand for intervention suggestions and pacing insights.",
      icon: BarChart3,
    },
    {
      id: 4,
      title: "Adaptive Lesson Planning",
      subtitle: "Recommend interventions",
      details:
        "SAMpai recommends tweaks and targeted practice based on performance signals. Expand for scaffold templates and differentiation playbooks.",
      icon: Lightbulb,
    },
    {
      id: 5,
      title: "AI-Generated Teaching Aids",
      subtitle: "Visuals and analogies",
      details:
        "Generate diagrams, visualizations, and relatable analogies customized to your unit objectives. Expand for export options and variants.",
      icon: Palette,
    },
    {
      id: 6,
      title: "Plagiarism & Similarity",
      subtitle: "Semantic checks",
      details:
        "Detect copy-paste and paraphrase via semantic similarity. Expand for threshold controls and actionable flags.",
      icon: Shield,
    },
    {
      id: 7,
      title: "Classroom Companion Mode",
      subtitle: "Summaries & FAQs",
      details:
        "Live summaries of discussions with automatic FAQs and follow-ups. Expand to configure prompts and handouts.",
      icon: MessageCircle,
    },
  ]

  const plasmaColor = theme === "dark" ? "#60a5fa" : "#3b82f6"

  return (
    <section id="teachers" ref={ref} className="relative py-20 sm:py-32 overflow-hidden">
      <div className="absolute inset-0 -z-10 opacity-80">
        <Plasma
          color={plasmaColor}
          speed={0.6}
          direction="forward"
          scale={1.08}
          opacity={0.6}
          mouseInteractive={false}
        />
      </div>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.8 }}
          className="text-center mb-14"
        >
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold mb-6 text-balance">
            Empowering{" "}
            <span className="bg-gradient-to-r from-chart-1 to-chart-2 bg-clip-text text-transparent">Teachers</span>{" "}
            with AI
          </h2>
          <p className="text-lg sm:text-xl text-muted-foreground max-w-3xl mx-auto leading-relaxed text-pretty">
            A modern toolkit to author faster, assess better, and discover insights—right inside your stack.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.96 }}
          animate={inView ? { opacity: 1, scale: 1 } : {}}
          transition={{ duration: 0.7 }}
          className="flex justify-center items-center px-2"
        >
          <div className="relative">
            <Stack
              cardsData={teacherCards}
              cardDimensions={cardDims}
              randomRotation={true}
              sensitivity={160}
              sendToBackOnClick={false}
              contentVariant="teacher"
            />
          </div>
        </motion.div>
      </div>
    </section>
  )
}
