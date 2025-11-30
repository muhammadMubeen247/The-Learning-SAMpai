"use client"

import { forwardRef, useEffect, useImperativeHandle, useRef } from "react"
import { gsap } from "gsap"

export type PixelTransitionHandle = {
  run: (onMidpoint?: () => void) => Promise<void>
}

type PixelTransitionProps = {
  gridSize?: number
  pixelColor?: string
  animationStepDuration?: number
  className?: string
}

/**
 * PixelCorruptionOverlay
 * - A controlled overlay that performs a "glitch/pixel corruption" swipe.
 * - Call ref.current.run(() => {...swap content...}) to execute the transition.
 * - Designed to sit inside a relatively positioned parent (the auth card).
 */
export const PixelCorruptionOverlay = forwardRef<PixelTransitionHandle, PixelTransitionProps>(
  ({ gridSize = 64, pixelColor = "hsl(var(--chart-2))", animationStepDuration = 0.5, className = "" }, ref) => {
    const overlayRef = useRef<HTMLDivElement | null>(null)
    const pixelsRef = useRef<HTMLDivElement | null>(null)

    // Build the pixel grid once or when gridSize/color changes
    useEffect(() => {
      const gridEl = pixelsRef.current
      if (!gridEl) return

      gridEl.innerHTML = ""
      const size = 100 / gridSize

      for (let row = 0; row < gridSize; row++) {
        for (let col = 0; col < gridSize; col++) {
          const pixel = document.createElement("div")
          pixel.style.position = "absolute"
          pixel.style.width = `${size}%`
          pixel.style.height = `${size}%`
          pixel.style.left = `${col * size}%`
          pixel.style.top = `${row * size}%`
          pixel.style.backgroundColor = pixelColor
          pixel.style.opacity = "0"
          pixel.style.transform = "scale(0.6)"
          gridEl.appendChild(pixel)
        }
      }
    }, [gridSize, pixelColor])

    useImperativeHandle(ref, () => ({
      run: (onMidpoint?: () => void) => {
        return new Promise<void>((resolve) => {
          if (!overlayRef.current || !pixelsRef.current) {
            onMidpoint?.()
            resolve()
            return
          }

          const overlay = overlayRef.current
          const pixels = Array.from(pixelsRef.current.children) as HTMLDivElement[]

          // Ensure overlay is visible
          gsap.set(overlay, { autoAlpha: 1, pointerEvents: "none" })

// Cover: pixels appear from center outward, smoothly
const half = animationStepDuration / 2
const tl = gsap.timeline({
  onComplete: () => {
    // Hide overlay smoothly
    gsap.set(overlay, { autoAlpha: 0 })
    resolve()
  },
})

// Reset before anim
gsap.set(pixels, {
  opacity: 0,
  scale: 0.6,
  willChange: "opacity, transform",
})

// First half: spread out
tl.to(pixels, {
  opacity: 1,
  scale: 1,
  duration: half,
  ease: "power3.out",
  stagger: {
    grid: [gridSize, gridSize],
    from: "center",
    amount: half * 0.9,
  },
})

// Midpoint swap
  .add(() => {
    onMidpoint?.()
  })

// Second half: retract smoothly *in the same order but reversed*
  .to(pixels, {
    opacity: 0,
    scale: 0.6,
    duration: half * 1.1, // slightly longer for smoother feel
    ease: "power2.inOut",
    stagger: {
      grid: [gridSize, gridSize],
      from: "center",
      amount: half * 0.9,
      each: 0.003,
      // key part: reverse order to make it retract smoothly
    },
    onStart: () => {
      // Optional: small delay between cover and uncover
      gsap.delayedCall(0.05, () => {})
    },
  })

        })
      },
    }))

    return (
      <div
        ref={overlayRef}
        className={`pointer-events-none absolute inset-0 z-40 ${className}`}
        style={{ opacity: 0 }}
        aria-hidden="true"
      >
        <div ref={pixelsRef} className="absolute inset-0" />
      </div>
    )
  },
)

PixelCorruptionOverlay.displayName = "PixelCorruptionOverlay"
