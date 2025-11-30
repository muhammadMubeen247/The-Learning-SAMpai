"use client"

import { useState } from "react"
import { Copy, Check } from "lucide-react"
import { motion } from "framer-motion"

type ClassroomCodeDisplayProps = {
  code: string
  isOwner: boolean
}

export default function ClassroomCodeDisplay({ code, isOwner }: ClassroomCodeDisplayProps) {
  if (!isOwner) {
    return null
  }
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      // Fallback for older browsers
      const textArea = document.createElement("textarea")
      textArea.value = code
      document.body.appendChild(textArea)
      textArea.select()
      document.execCommand("copy")
      document.body.removeChild(textArea)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-card/80 backdrop-blur-md shadow-lg">
      <span className="text-xs text-muted-foreground">Code:</span>
      <span className="text-xs font-mono font-semibold text-foreground">{code}</span>
      <button
        type="button"
        onClick={handleCopy}
        className="flex items-center gap-1 px-2 py-1 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer transition-colors"
        aria-label="Copy classroom code"
      >
        {copied ? (
          <Check className="size-3.5 text-chart-1" />
        ) : (
          <Copy className="size-3.5 text-foreground" />
        )}
      </button>
    </div>
  )
}

