"use client"

import type React from "react"
import { useCallback, useMemo, useRef, useState, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"
import { Check, X, Eye, EyeOff } from "lucide-react"
import { PixelCorruptionOverlay, type PixelTransitionHandle } from "@/components/backgrounds/pixel-transition"
import { useRouter, usePathname } from "next/navigation"
import API from "@/api/axios" // 👈 Import your axios instance

type Mode = "signup" | "login"

interface AuthCardProps {
  initialMode?: Mode
}

type RuleKey = "length" | "upper" | "lower" | "number" | "special" | "match"

export function AuthCard({ initialMode = "signup" }: AuthCardProps) {
  const [mode, setMode] = useState<Mode>(initialMode)
  const [isSwiping, setIsSwiping] = useState(false)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const overlayRef = useRef<PixelTransitionHandle | null>(null)
  const router = useRouter()
  const pathname = usePathname()

  // Signup state
  const [username, setUsername] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")

  // Login state
  const [loginEmail, setLoginEmail] = useState("")
  const [loginPassword, setLoginPassword] = useState("")

  // Password visibility toggles
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [showLoginPassword, setShowLoginPassword] = useState(false)

  // Password validation
  const passwordRules = useMemo(() => {
    const rules: Record<RuleKey, boolean> = {
      length: password.length >= 8,
      upper: /[A-Z]/.test(password),
      lower: /[a-z]/.test(password),
      number: /[0-9]/.test(password),
      special: /[^A-Za-z0-9]/.test(password),
      match: confirm.length > 0 && password === confirm,
    }
    return rules
  }, [password, confirm])

  const satisfiedCount = useMemo(() => {
    return (
      (passwordRules.length ? 1 : 0) +
      (passwordRules.upper ? 1 : 0) +
      (passwordRules.lower ? 1 : 0) +
      (passwordRules.number ? 1 : 0) +
      (passwordRules.special ? 1 : 0)
    )
  }, [passwordRules])

  const progressPct = (satisfiedCount / 5) * 100
  const canSignUp =
    satisfiedCount === 5 && passwordRules.match && username.trim().length > 0 && /\S+@\S+\.\S+/.test(email)
  const canLogin = /\S+@\S+\.\S+/.test(loginEmail) && loginPassword.length >= 1

  const triggerSwipe = useCallback(
    async (nextMode?: Mode) => {
      if (isSwiping) return
      setIsSwiping(true)
      const target = nextMode ?? (mode === "signup" ? "login" : "signup")
      await overlayRef.current?.run(() => {
        setMode(target)
        router.push(target === "login" ? "/login" : "/signup")
      })
      setIsSwiping(false)
    },
    [isSwiping, mode, router],
  )

  // ✅ Signup submission (Axios integrated)
  const onSubmitSignup = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSignUp || loading) return
    setLoading(true)
    setMessage(null)
    try {
      const res = await API.post("/auth/signup", {
        username,
        email,
        password,
      })
      setMessage("Signup successful! Redirecting to login...")
      // Smoothly transition after signup
      await overlayRef.current?.run(() => {
        setMode("login")
        router.push("/login")
      })
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      let friendly = "Signup failed. Please try again."
      if (typeof detail === "string") {
        friendly = detail
      } else if (Array.isArray(detail)) {
        // FastAPI/Pydantic validation errors are usually arrays of {loc, msg, type, ctx}
        friendly = detail.map((d: any) => d?.msg ?? JSON.stringify(d)).join("; ")
      }
      setMessage(friendly)
    } finally {
      setLoading(false)
    }
  }

  // ✅ Login submission (Axios integrated)
  const onSubmitLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canLogin || loading) return
    setLoading(true)
    setMessage(null)
    try {
      const res = await API.post("/auth/login", {
        email: loginEmail,
        password: loginPassword,
      })
      localStorage.setItem("token", res.data.access_token)
      if (res.data.user) {
        localStorage.setItem("user", JSON.stringify(res.data.user))
      }
      setMessage("Login successful! Redirecting...")
      router.push("/dashboard")
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      let friendly = "Login failed. Check your credentials."
      if (typeof detail === "string") {
        friendly = detail
      } else if (Array.isArray(detail)) {
        friendly = detail.map((d: any) => d?.msg ?? JSON.stringify(d)).join("; ")
      }
      setMessage(friendly)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative w-full flex items-center justify-center overflow-hidden">
      <div className="relative w-full max-w-md">
        <div className="relative rounded-2xl border border-primary/20 bg-card/80 backdrop-blur-xl shadow-[0_0_0_1px_inset_var(--color-primary)] ring-1 ring-border/40">
          <div className="absolute -inset-px rounded-2xl pointer-events-none bg-gradient-to-br from-chart-1/20 via-transparent to-chart-2/20" />
          <div className="relative p-6 sm:p-8">
            <div className="mb-6 text-center">
              <h1 className="text-2xl font-semibold">
                {mode === "signup" ? "Create your account" : "Welcome back"}
              </h1>
              <p className="text-sm text-muted-foreground mt-2">
                {mode === "signup" ? "Join the learning revolution" : "Log in to continue your journey"}
              </p>
            </div>

            {/* ✨ Animated Forms */}
            <AnimatePresence mode="wait" initial={false}>
              {mode === "signup" ? (
                <motion.form
                  key="signup"
                  initial={{ opacity: 0, y: 10, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -8, scale: 0.98 }}
                  transition={{ duration: 0.25, ease: "easeOut" }}
                  onSubmit={onSubmitSignup}
                  className="space-y-4"
                >
                  <div className="space-y-2">
                    <Label htmlFor="username">Username</Label>
                    <Input
                      id="username"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      placeholder="sampai_user"
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="email">Email</Label>
                    <Input
                      id="email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@example.com"
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="password">Password</Label>
                    <div className="relative">
                      <Input
                        id="password"
                        type={showPassword ? "text" : "password"}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="••••••••"
                        required
                        className="pr-10"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                        aria-label={showPassword ? "Hide password" : "Show password"}
                      >
                        {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="confirm">Confirm password</Label>
                    <div className="relative">
                      <Input
                        id="confirm"
                        type={showConfirmPassword ? "text" : "password"}
                        value={confirm}
                        onChange={(e) => setConfirm(e.target.value)}
                        placeholder="••••••••"
                        required
                        className="pr-10"
                      />
                      <button
                        type="button"
                        onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                        aria-label={showConfirmPassword ? "Hide password" : "Show password"}
                      >
                        {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>

                  {/* Password strength meter */}
                  <div className="space-y-3">
                    <div className="h-2 rounded-full bg-muted overflow-hidden">
                      <div
                        className={cn(
                          "h-full rounded-full transition-all",
                          satisfiedCount <= 1 && "bg-destructive/70",
                          satisfiedCount === 2 && "bg-destructive/50",
                          satisfiedCount === 3 && "bg-chart-2/70",
                          satisfiedCount === 4 && "bg-chart-2",
                          satisfiedCount === 5 && "bg-chart-1",
                        )}
                        style={{ width: `${progressPct}%` }}
                      />
                    </div>
                    <ul className="grid grid-cols-2 gap-2 text-xs">
                      <RuleItem ok={passwordRules.length} label="8+ characters" className="col-span-2" />
                      <RuleItem ok={passwordRules.upper} label="One uppercase" />
                      <RuleItem ok={passwordRules.lower} label="One lowercase" />
                      <RuleItem ok={passwordRules.number} label="One number" />
                      <RuleItem ok={passwordRules.special} label="One special character" />
                    </ul>
                  </div>

                  {/* Feedback message */}
                  {message && <p className="text-sm text-center text-muted-foreground">{message}</p>}

                  <Button
                    type="submit"
                    className="w-full bg-gradient-to-r from-chart-1 to-chart-2 hover:opacity-90 transition-all"
                    disabled={!canSignUp || isSwiping || loading}
                  >
                    {loading ? "Signing up..." : "Sign up"}
                  </Button>

                  <p className="text-sm text-center text-muted-foreground">
                    Already have an account?{" "}
                    <button
                      type="button"
                      className="text-foreground underline-offset-4 hover:underline"
                      onClick={() => triggerSwipe("login")}
                    >
                      Log in
                    </button>
                  </p>
                </motion.form>
              ) : (
                <motion.form
                  key="login"
                  initial={{ opacity: 0, y: 10, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -8, scale: 0.98 }}
                  transition={{ duration: 0.25, ease: "easeOut" }}
                  onSubmit={onSubmitLogin}
                  className="space-y-4"
                >
                  <div className="space-y-2">
                    <Label htmlFor="lemail">Email</Label>
                    <Input
                      id="lemail"
                      type="email"
                      value={loginEmail}
                      onChange={(e) => setLoginEmail(e.target.value)}
                      placeholder="you@example.com"
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="lpassword">Password</Label>
                    <div className="relative">
                      <Input
                        id="lpassword"
                        type={showLoginPassword ? "text" : "password"}
                        value={loginPassword}
                        onChange={(e) => setLoginPassword(e.target.value)}
                        placeholder="••••••••"
                        required
                        className="pr-10"
                      />
                      <button
                        type="button"
                        onClick={() => setShowLoginPassword(!showLoginPassword)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                        aria-label={showLoginPassword ? "Hide password" : "Show password"}
                      >
                        {showLoginPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>

                  {message && <p className="text-sm text-center text-muted-foreground">{message}</p>}

                  <Button
                    type="submit"
                    className="w-full bg-gradient-to-r from-chart-1 to-chart-2 hover:opacity-90 transition-all"
                    disabled={!canLogin || isSwiping || loading}
                  >
                    {loading ? "Logging in..." : "Log in"}
                  </Button>

                  <p className="text-sm text-center text-muted-foreground">
                    Don{"'"}t have an account yet?{" "}
                    <button
                      type="button"
                      className="text-foreground underline-offset-4 hover:underline"
                      onClick={() => triggerSwipe("signup")}
                    >
                      Sign up
                    </button>
                  </p>
                </motion.form>
              )}
            </AnimatePresence>

            {/* Pixel swipe overlay */}
            <PixelCorruptionOverlay
              ref={overlayRef}
              gridSize={25}
              animationStepDuration={0.6}
              pixelColor="color-mix(in oklch, var(--color-chart-1) 70%, var(--color-chart-2))"
            />
          </div>
        </div>
      </div>
    </div>
  )
}

function RuleItem({ ok, label, className }: { ok: boolean; label: string; className?: string }) {
  return (
    <li
      className={cn(
        "flex items-center gap-2 rounded-md px-2 py-1.5 border",
        ok ? "border-chart-1/40 bg-chart-1/10 text-foreground" : "border-border bg-muted/40 text-muted-foreground",
        className,
      )}
    >
      <div className={cn("h-5 w-5 rounded-full flex items-center justify-center", ok ? "bg-chart-1/70" : "bg-muted")}>
        {ok ? <Check className="h-3.5 w-3.5 text-primary-foreground" /> : <X className="h-3.5 w-3.5 text-muted-foreground" />}
      </div>
      <span className="text-xs">{label}</span>
    </li>
  )
}
