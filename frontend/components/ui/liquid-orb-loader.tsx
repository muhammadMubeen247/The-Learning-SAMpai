"use client"

import React, { useEffect, useRef, useState } from "react"
import { Renderer, Program, Mesh, Triangle, Vec3 } from "ogl"

interface LiquidOrbProps {
  value?: number;          // 0 to 100
  hue?: number;            // Color shift
  hoverIntensity?: number; // How much it wobbles (even without mouse)
  rotateOnHover?: boolean; // Whether it spins
  forceHoverState?: boolean; 
  className?: string;
  size?: "sm" | "md" | "lg" | "xl";
}

const sizeMap = {
  sm: "w-16 h-16",
  md: "w-32 h-32",
  lg: "w-64 h-64",
  xl: "w-96 h-96",
}

/**
 * LiquidOrb Component
 * Renders the "Energy Orb" shader with a liquid filling effect that matches the border texture.
 */
function LiquidOrb({ 
  value = 0, 
  hue = 0, 
  hoverIntensity = 0.2, 
  rotateOnHover = true, 
  forceHoverState = false,
  className = "",
  size = "md"
}: LiquidOrbProps) {
  const ctnDom = useRef<HTMLDivElement>(null)
  
  // Refs for logic/animation
  const progressRef = useRef(value)
  const glRef = useRef<any>(null)
  const rafRef = useRef<number>(0)
  const resizeObserverRef = useRef<ResizeObserver | null>(null)
  
  // Track time and rotation manually for the loop
  const rotRef = useRef(0)
  // Update ref when prop changes
  useEffect(() => {
    progressRef.current = value
  }, [value])

  /* -------------------------------------------------------------------------- */
  /* SHADER CODE                                                               */
  /* -------------------------------------------------------------------------- */
  const vert = /* glsl */ `
    precision highp float;
    attribute vec2 position;
    attribute vec2 uv;
    varying vec2 vUv;
    void main() {
      vUv = uv;
      gl_Position = vec4(position, 0.0, 1.0);
    }
  `

  const frag = /* glsl */ `
    precision highp float;
    uniform float iTime;
    uniform vec3 iResolution;
    uniform float hue;
    uniform float hover;
    uniform float rot;
    uniform float hoverIntensity;
    uniform float uProgress; // 0.0 to 1.0
    varying vec2 vUv;
    // --- HELPER FUNCTIONS ---
    vec3 rgb2yiq(vec3 c) {
      float y = dot(c, vec3(0.299, 0.587, 0.114));
      float i = dot(c, vec3(0.596, -0.274, -0.322));
      float q = dot(c, vec3(0.211, -0.523, 0.312));
      return vec3(y, i, q);
    }
    
    vec3 yiq2rgb(vec3 c) {
      float r = c.x + 0.956 * c.y + 0.621 * c.z;
      float g = c.x - 0.272 * c.y - 0.647 * c.z;
      float b = c.x - 1.106 * c.y + 1.703 * c.z;
      return vec3(r, g, b);
    }
    
    vec3 adjustHue(vec3 color, float hueDeg) {
      float hueRad = hueDeg * 3.14159265 / 180.0;
      vec3 yiq = rgb2yiq(color);
      float cosA = cos(hueRad);
      float sinA = sin(hueRad);
      float i = yiq.y * cosA - yiq.z * sinA;
      float q = yiq.y * sinA + yiq.z * cosA;
      yiq.y = i;
      yiq.z = q;
      return yiq2rgb(yiq);
    }
    vec3 hash33(vec3 p3) {
      p3 = fract(p3 * vec3(0.1031, 0.11369, 0.13787));
      p3 += dot(p3, p3.yxz + 19.19);
      return -1.0 + 2.0 * fract(vec3(
        p3.x + p3.y,
        p3.x + p3.z,
        p3.y + p3.z
      ) * p3.zyx);
    }
    float snoise3(vec3 p) {
      const float K1 = 0.333333333;
      const float K2 = 0.166666667;
      vec3 i = floor(p + (p.x + p.y + p.z) * K1);
      vec3 d0 = p - (i - (i.x + i.y + i.z) * K2);
      vec3 e = step(vec3(0.0), d0 - d0.yzx);
      vec3 i1 = e * (1.0 - e.zxy);
      vec3 i2 = 1.0 - e.zxy * (1.0 - e);
      vec3 d1 = d0 - (i1 - K2);
      vec3 d2 = d0 - (i2 - K1);
      vec3 d3 = d0 - 0.5;
      vec4 h = max(0.6 - vec4(
        dot(d0, d0),
        dot(d1, d1),
        dot(d2, d2),
        dot(d3, d3)
      ), 0.0);
      vec4 n = h * h * h * h * vec4(
        dot(d0, hash33(i)),
        dot(d1, hash33(i + i1)),
        dot(d2, hash33(i + i2)),
        dot(d3, hash33(i + 1.0))
      );
      return dot(vec4(31.316), n);
    }
    vec4 extractAlpha(vec3 colorIn) {
      float a = max(max(colorIn.r, colorIn.g), colorIn.b);
      return vec4(colorIn.rgb / (a + 1e-5), a);
    }
    // Brighter, more vibrant colors
    const vec3 baseColor1 = vec3(0.7, 0.3, 1.0);
    const vec3 baseColor2 = vec3(0.4, 0.8, 1.0);
    const vec3 baseColor3 = vec3(0.1, 0.2, 0.8);
    const vec3 cFoamGlow = vec3(0.6, 0.9, 1.0); // Bright energy color for foam
    const float innerRadius = 0.6;
    const float noiseScale = 0.65;
    float light1(float intensity, float attenuation, float dist) {
      return intensity / (1.0 + dist * attenuation);
    }
    float light2(float intensity, float attenuation, float dist) {
      return intensity / (1.0 + dist * dist * attenuation);
    }
    // --- MAIN DRAW LOGIC ---
    vec4 draw(vec2 uv, vec2 originalUv) {
      // 1. SHELL (Border) CALCULATIONS
      // We use 'uv' (which includes rotation) for the shell shape so it spins.
      vec3 color1 = adjustHue(baseColor1, hue);
      vec3 color2 = adjustHue(baseColor2, hue);
      vec3 color3 = adjustHue(baseColor3, hue);
      
      float ang = atan(uv.y, uv.x);
      float len = length(uv);
      float invLen = len > 0.0 ? 1.0 / len : 0.0;
      
      float n0 = snoise3(vec3(uv * noiseScale, iTime * 0.5)) * 0.5 + 0.5;
      float r0 = mix(mix(innerRadius, 1.0, 0.4), mix(innerRadius, 1.0, 0.6), n0);
      
      // Shell Lighting
      float d0 = distance(uv, (r0 * invLen) * uv);
      float v0 = light1(1.0, 10.0, d0);
      v0 *= smoothstep(r0 * 1.05, r0, len);
      float cl = cos(ang + iTime * 2.0) * 0.5 + 0.5;
      
      // Rotating highlight
      float a = iTime * -1.0;
      vec2 pos = vec2(cos(a), sin(a)) * r0;
      float d = distance(uv, pos);
      float v1 = light2(1.5, 5.0, d);
      v1 *= light1(1.0, 50.0, d0);
      
      // Ring Masks
      float v2 = smoothstep(1.0, mix(innerRadius, 1.0, n0 * 0.5), len);
      float v3 = smoothstep(innerRadius, mix(innerRadius, 1.0, 0.5), len);
      
      // Shell Color Composition
      vec3 col = mix(color1, color2, cl);
      col = mix(color3, col, v0);
      col = (col + v1) * v2 * v3;
      col = clamp(col, 0.0, 1.0);
      // 2. LIQUID CALCULATIONS
      
      // Liquid Level: Use ORIGINAL UV.y (screen space) so gravity is down
      float liquidLevel = mix(-1.1, 1.1, uProgress); 
      float wave = sin(originalUv.x * 5.0 + iTime * 2.0) * 0.05 
                 + sin(originalUv.x * 11.0 + iTime * 3.5) * 0.02;
      float fillHeight = liquidLevel + wave;
      float liquidMask = smoothstep(fillHeight + 0.02, fillHeight, originalUv.y);
      
      // Container Mask: Use ROTATED 'uv' to match the wobbly shell boundary
      float containerMask = smoothstep(r0, r0 - 0.01, len);
      float finalLiquidMask = liquidMask * containerMask;
      // Liquid Texture: Match Border
      // We use originalUv for the texture coordinates so the "plasma" doesn't spin
      // It just flows.
      float liquidNoise = snoise3(vec3(originalUv * noiseScale * 1.5, iTime * 0.4)) * 0.5 + 0.5;
      
      // Use similar color mixing logic to the border to match texture
      vec3 lCol = mix(color1, color2, liquidNoise);
      
      // Add a second layer of noise for depth
      float liquidNoise2 = snoise3(vec3(originalUv * 2.0, iTime * 0.8));
      lCol = mix(lCol, color3, liquidNoise2 * 0.5 + 0.5);
      
      // Add "energy" highlights similar to border
      lCol += vec3(0.2) * smoothstep(0.6, 0.9, liquidNoise);
      
      // Foam Line (Bright edge at the top of liquid)
      float foamMask = smoothstep(fillHeight + 0.06, fillHeight + 0.02, originalUv.y) * containerMask;
      foamMask -= finalLiquidMask;
      foamMask = clamp(foamMask, 0.0, 1.0);
      
      // 3. FINAL COMPOSITION
      
      // Start with shell color
      vec3 finalColor = col;
      float finalAlpha = extractAlpha(col).a;
      // Blend liquid behind the shell (or effectively 'inside' since shell has transparency)
      
      // Make liquid more translucent (like glass/energy fluid)
      float liquidAlphaFactor = 0.7; // Increased opacity
      if (finalLiquidMask > 0.01) {
          // If we are in the liquid area
          // Scale the opacity down to make it translucent
          float effectiveAlpha = finalLiquidMask * liquidAlphaFactor;
          
          finalColor = mix(finalColor, lCol, effectiveAlpha);
          finalAlpha = max(finalAlpha, effectiveAlpha); 
      }
      // Add foam on top
      // Use a bright energy color for the foam instead of pure white
      vec3 foamColor = adjustHue(cFoamGlow, hue);
      finalColor = mix(finalColor, foamColor, foamMask);
      finalAlpha = max(finalAlpha, foamMask);
      return vec4(finalColor, finalAlpha);
    }
    vec4 mainImage(vec2 fragCoord) {
      vec2 center = iResolution.xy * 0.5;
      float size = min(iResolution.x, iResolution.y);
      
      // 1. Original UV (Screen Space) - Used for Liquid Level & Texture
      vec2 originalUv = (fragCoord - center) / size * 2.0;
      
      // 2. Rotated UV - Used for Shell Shape & Container Boundary
      vec2 uv = originalUv;
      float angle = rot;
      float s = sin(angle);
      float c = cos(angle);
      uv = vec2(c * uv.x - s * uv.y, s * uv.x + c * uv.y);
      
      // Apply Hover Distortion to BOTH or just Shell?
      // Usually the field distorts everything.
      vec2 distortion = vec2(
        sin(uv.y * 10.0 + iTime),
        sin(uv.x * 10.0 + iTime)
      ) * hover * hoverIntensity * 0.1;
      uv += distortion;
      originalUv += distortion; // Apply distortion to liquid too so it wobbles with the bubble
      
      return draw(uv, originalUv);
    }
    void main() {
      vec2 fragCoord = vUv * iResolution.xy;
      vec4 col = mainImage(fragCoord);
      gl_FragColor = vec4(col.rgb * col.a, col.a);
    }
  `

  useEffect(() => {
    const container = ctnDom.current
    if (!container) return

    let isMounted = true
    let renderer: any, program: any, mesh: any

    const init = () => {
      if (!isMounted) return

      try {
        renderer = new Renderer({
          alpha: true,
          premultipliedAlpha: false,
          antialias: true,
          powerPreference: "high-performance",
          dpr: Math.min(window.devicePixelRatio || 1, 2),
        })
        
        const gl = renderer.gl
        gl.clearColor(0, 0, 0, 0)
        container.appendChild(gl.canvas)
        glRef.current = gl
        const geometry = new Triangle(gl)
        
        program = new Program(gl, {
          vertex: vert,
          fragment: frag,
          uniforms: {
            iTime: { value: 0 },
            iResolution: {
              value: new Vec3(gl.canvas.width, gl.canvas.height, gl.canvas.width / gl.canvas.height),
            },
            hue: { value: hue },
            hover: { value: 0 }, 
            rot: { value: 0 },
            hoverIntensity: { value: hoverIntensity },
            uProgress: { value: progressRef.current / 100 },
          },
        })
        mesh = new Mesh(gl, { geometry, program })
        const resize = () => {
          if (!container || !gl.canvas) return
          const width = container.clientWidth
          const height = container.clientHeight
          renderer.setSize(width, height)
          
          program.uniforms.iResolution.value.set(
            gl.drawingBufferWidth,
            gl.drawingBufferHeight,
            gl.drawingBufferWidth / gl.drawingBufferHeight,
          )
        }
        
        const resizeObserver = new ResizeObserver(() => resize())
        resizeObserver.observe(container)
        resizeObserverRef.current = resizeObserver
        resize()
        let lastTime = performance.now()
        // Animation params
        const rotationBoost = 0.35
        const baseRotation = 0.1
        const hoverSmoothing = 0.06
        let currentHover = 0
        const update = (t: number) => {
          rafRef.current = requestAnimationFrame(update)
          
          const dt = Math.min((t - lastTime) * 0.001, 0.033)
          lastTime = t
          
          if (program) {
             program.uniforms.iTime.value = t * 0.001
             program.uniforms.hue.value = hue
             program.uniforms.hoverIntensity.value = hoverIntensity
             
             const targetProgress = progressRef.current / 100
             const currentProgress = program.uniforms.uProgress.value
             program.uniforms.uProgress.value += (targetProgress - currentProgress) * 0.05
             
             // Simulate Hover
             const targetHoverState = forceHoverState ? 1 : 1; 
             currentHover += (targetHoverState - currentHover) * hoverSmoothing
             program.uniforms.hover.value = currentHover
             // Rotation
             const rotSpeed = rotateOnHover ? baseRotation + currentHover * rotationBoost : 0
             rotRef.current += dt * rotSpeed
             program.uniforms.rot.value = rotRef.current
          }
          if (renderer && mesh) {
             renderer.render({ scene: mesh })
          }
        }
        rafRef.current = requestAnimationFrame(update)
      } catch (e) {
        console.error("Failed to load OGL:", e)
      }
    }
    init()
    return () => {
      isMounted = false
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      if (resizeObserverRef.current) resizeObserverRef.current.disconnect()
      
      const gl = glRef.current
      if (gl && gl.canvas && gl.canvas.parentNode === container) {
        container.removeChild(gl.canvas)
      }
      if (gl) gl.getExtension("WEBGL_lose_context")?.loseContext()
    }
  }, [hue, hoverIntensity, rotateOnHover, forceHoverState]) 

  return <div ref={ctnDom} className={`${sizeMap[size]} ${className}`} />
}

interface LoadingOrbProps {
  progress?: number;
  size?: "sm" | "md" | "lg" | "xl";
  className?: string;
  message?: string;
  showProgress?: boolean;
}

/**
 * LoadingOrb - A loading component using LiquidOrb with progress indication
 */
export function LoadingOrb({ 
  progress = 0, 
  size = "md",
  className = "",
  message,
  showProgress = false
}: LoadingOrbProps) {
  const [animatedProgress, setAnimatedProgress] = useState(0)

  useEffect(() => {
    // Smoothly animate progress changes
    const interval = setInterval(() => {
      setAnimatedProgress((prev) => {
        const diff = progress - prev
        if (Math.abs(diff) < 0.5) return progress
        return prev + diff * 0.1
      })
    }, 16) // ~60fps

    return () => clearInterval(interval)
  }, [progress])

  return (
    <div className={`flex flex-col items-center justify-center gap-4 ${className}`}>
      <LiquidOrb 
        value={animatedProgress} 
        className="w-full h-full" 
        hue={0}
        hoverIntensity={0.2}
        rotateOnHover={true}
        size={size}
      />
      {message && (
        <p className="text-sm text-muted-foreground text-center">{message}</p>
      )}
      {showProgress && (
        <p className="text-xs text-muted-foreground">{Math.round(animatedProgress)}%</p>
      )}
    </div>
  )
}

/**
 * LoadingOverlay - Full screen or container loading overlay
 */
interface LoadingOverlayProps {
  isLoading: boolean;
  progress?: number;
  message?: string;
  size?: "sm" | "md" | "lg" | "xl";
  fullScreen?: boolean;
}

export function LoadingOverlay({ 
  isLoading, 
  progress = 0,
  message,
  size = "lg",
  fullScreen = false
}: LoadingOverlayProps) {
  if (!isLoading) return null

  const containerClass = fullScreen 
    ? "fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center"
    : "absolute inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center"

  return (
    <div className={containerClass}>
      <LoadingOrb 
        progress={progress}
        size={size}
        message={message}
        showProgress={progress > 0 && progress < 100}
      />
    </div>
  )
}

export default LiquidOrb

