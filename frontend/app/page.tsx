import { Navbar } from "@/components/landingpage/navbar"
import { HeroSection } from "@/components/landingpage/hero-section"
import { ProblemSection } from "@/components/landingpage/problem-section"
import { SolutionSection } from "@/components/landingpage/solution-section"
import { FeaturesSection } from "@/components/landingpage/features-section"
import { TeacherSection } from "@/components/landingpage/teacher-section"
import { HowItWorksSection } from "@/components/landingpage/how-it-works-section"
import { CTASection } from "@/components/landingpage/cta-section"
import { Footer } from "@/components/landingpage/footer"
import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Home",
  description: "Transform your learning experience with AI-powered classrooms, intelligent document processing, and personalized topic extraction.",
}

export default function Home() {
  return (
    <main className="min-h-screen">
      <Navbar />
      <HeroSection />
      <ProblemSection />
      <SolutionSection />
      <FeaturesSection />
      <TeacherSection />
      <HowItWorksSection />
      <CTASection />
      <Footer />
    </main>
  )
}
