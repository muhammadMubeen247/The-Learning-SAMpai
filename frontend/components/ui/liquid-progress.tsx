"use client"

import { motion } from "framer-motion"

interface LiquidProgressProps {
  progress: number // 0-100
  label?: string
  className?: string
}

export default function LiquidProgress({ progress, label, className = "" }: LiquidProgressProps) {
  const clampedProgress = Math.max(0, Math.min(100, progress))

  return (
    <div className={`w-full ${className}`}>
      {label && (
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-foreground/80">{label}</span>
          <span className="text-sm font-medium text-foreground">{Math.round(clampedProgress)}%</span>
        </div>
      )}
      <div className="relative w-full h-2 bg-background/20 rounded-full overflow-hidden">
        <motion.div
          className="absolute inset-y-0 left-0 bg-gradient-to-r from-[color-mix(in_oklab,var(--chart-1),transparent_20%)] via-[color-mix(in_oklab,var(--chart-1),transparent_10%)] to-[color-mix(in_oklab,var(--chart-2),transparent_20%)]"
          initial={{ width: 0 }}
          animate={{ width: `${clampedProgress}%` }}
          transition={{ duration: 0.3, ease: "easeOut" }}
        >
          {/* Liquid wave effect */}
          <motion.div
            className="absolute inset-0 opacity-30"
            style={{
              background: `linear-gradient(90deg, 
                transparent 0%, 
                rgba(255,255,255,0.3) 50%, 
                transparent 100%)`,
            }}
            animate={{
              x: ["-100%", "200%"],
            }}
            transition={{
              duration: 2,
              repeat: Infinity,
              ease: "linear",
            }}
          />
        </motion.div>
      </div>
    </div>
  )
}

