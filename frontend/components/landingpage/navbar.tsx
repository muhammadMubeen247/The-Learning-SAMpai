"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import ThemeToggle from "@/components/theme/theme-toggle"
import { Menu, X } from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"
import { useTheme } from "@/hooks/use-theme"
import { useRouter } from "next/navigation"
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu"

type NavbarProps = {
  variant?: "full" | "minimal"
  username?: string
  onLogout?: () => void
  actions?: React.ReactNode
}

export function Navbar({ variant = "full", username = "User", onLogout, actions }: NavbarProps) {
  const { theme } = useTheme()
  const [isScrolled, setIsScrolled] = useState(false)
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const router = useRouter()

  const scrollTo = (id: string) => {
    if (variant === "minimal") return
    const el = document.getElementById(id)
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" })
      setIsMobileMenuOpen(false)
    }
  }

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 20)
    }
    window.addEventListener("scroll", handleScroll)
    return () => window.removeEventListener("scroll", handleScroll)
  }, [])

  return (
    <motion.nav
      key={theme}
      initial={{ y: -100 }}
      animate={{ y: 0 }}
      transition={{ duration: 0.6, ease: "easeOut" }}
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        isScrolled ? "bg-background/80 backdrop-blur-xl border-b border-border/50" : "bg-transparent"
      }`}
    >
      <div className="w-full px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16 sm:h-20">
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.2, duration: 0.5 }}
            className="flex items-center space-x-2"
          >
            <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-lg bg-gradient-to-br from-primary via-(--chart-1) to-(--chart-2) flex items-center justify-center">
              <span className="text-lg sm:text-xl font-bold text-primary-foreground">S</span>
            </div>
            <span className="text-lg sm:text-xl font-bold bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">
              The Learning SAMpai
            </span>
          </motion.div>

          {/* Desktop Navigation */}
          {variant === "full" ? (
            <div className="hidden md:flex items-center space-x-6">
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3, duration: 0.5 }}
                className="flex items-center space-x-1"
              >
                <ThemeToggle />
                <Button
                  variant="ghost"
                  className="text-sm font-medium cursor-pointer"
                  onClick={() => scrollTo("features")}
                >
                  Features
                </Button>
                <Button
                  variant="ghost"
                  className="text-sm font-medium cursor-pointer"
                  onClick={() => scrollTo("teachers")}
                >
                  For Teachers
                </Button>
                <Button
                  variant="ghost"
                  className="text-sm font-medium cursor-pointer"
                  onClick={() => scrollTo("how-it-works")}
                >
                  How it works
                </Button>
              </motion.div>
              <motion.div
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.4, duration: 0.5 }}
                className="flex items-center space-x-3"
              >
                <Button
                  variant="ghost"
                  className="text-sm font-medium cursor-pointer"
                  onClick={() => router.push("/login")}
                >
                  Log in
                </Button>
                <Button
                  className="text-sm font-medium cursor-pointer bg-gradient-to-r from-(--chart-1) to-(--chart-2) hover:opacity-90 transition-opacity"
                  onClick={() => router.push("/signup")}
                >
                  Sign up
                </Button>
              </motion.div>
            </div>
          ) : (
            <div className="hidden md:flex items-center space-x-2">
              {actions}
              <ThemeToggle />
              <DropdownMenu>
                <DropdownMenuTrigger>
                  <div className="flex items-center gap-2 cursor-pointer">
                    <div
                      aria-hidden
                      className="size-8 rounded-full bg-gradient-to-br from-(--chart-1) to-(--chart-2) ring-1 ring-border/50 shadow-inner"
                    />
                    <span className="text-sm text-foreground/80">{username}</span>
                  </div>
                </DropdownMenuTrigger>
                <DropdownMenuContent className="w-72">
                  <div className="flex flex-col items-center gap-3 px-4 py-4">
                    <div
                      aria-hidden
                      className="size-16 rounded-full bg-gradient-to-br from-(--chart-1) to-(--chart-2) ring-1 ring-border/50 shadow-inner"
                    />
                    <span className="text-base font-semibold text-foreground">{username}</span>
                  </div>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={onLogout}
                    className="cursor-pointer text-red-500 focus:text-red-500 hover:text-red-500"
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 24 24"
                      fill="currentColor"
                      className="size-4 mr-2"
                      aria-hidden
                    >
                      <path d="M16 13v-2H7V8l-5 4 5 4v-3h9zM20 3h-8v2h8v14h-8v2h8a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2z" />
                    </svg>
                    <span>Log out</span>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          )}

          {/* Mobile Right Controls */}
          <div className="flex md:hidden items-center space-x-2">
            {actions}
            <ThemeToggle />
            {variant === "full" ? (
              <Button variant="ghost" size="icon" onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}>
                {isMobileMenuOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
              </Button>
            ) : (
              <DropdownMenu>
                <DropdownMenuTrigger>
                  <div className="flex items-center gap-2 cursor-pointer">
                    <div
                      aria-hidden
                      className="size-8 rounded-full bg-gradient-to-br from-(--chart-1) to-(--chart-2) ring-1 ring-border/50 shadow-inner"
                    />
                    <span className="text-sm text-foreground/80">{username}</span>
                  </div>
                </DropdownMenuTrigger>
                <DropdownMenuContent className="w-72">
                  <div className="flex flex-col items-center gap-3 px-4 py-4">
                    <div
                      aria-hidden
                      className="size-16 rounded-full bg-gradient-to-br from-(--chart-1) to-(--chart-2) ring-1 ring-border/50 shadow-inner"
                    />
                    <span className="text-base font-semibold text-foreground">{username}</span>
                  </div>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={onLogout}
                    className="cursor-pointer text-red-500 focus:text-red-500 hover:text-red-500"
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 24 24"
                      fill="currentColor"
                      className="size-4 mr-2"
                      aria-hidden
                    >
                      <path d="M16 13v-2H7V8l-5 4 5 4v-3h9zM20 3h-8v2h8v14h-8v2h8a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2z" />
                    </svg>
                    <span>Log out</span>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        </div>
      </div>

      {/* Mobile Menu (only for full variant) */}
      {variant === "full" && (
        <AnimatePresence>
          {isMobileMenuOpen && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.3 }}
              className="md:hidden bg-background/95 backdrop-blur-xl border-b border-border/50"
            >
              <div className="w-full px-4 py-4 space-y-3">
                <Button
                  variant="ghost"
                  className="w-full justify-start cursor-pointer"
                  onClick={() => scrollTo("features")}
                >
                  Features
                </Button>
                <Button
                  variant="ghost"
                  className="w-full justify-start cursor-pointer"
                  onClick={() => scrollTo("teachers")}
                >
                  For Teachers
                </Button>
                <Button
                  variant="ghost"
                  className="w-full justify-start cursor-pointer"
                  onClick={() => scrollTo("how-it-works")}
                >
                  How it works
                </Button>
                <div className="pt-3 border-t border-border/50 space-y-2">
                  <Button
                    variant="ghost"
                    className="w-full cursor-pointer"
                    onClick={() => (setIsMobileMenuOpen(false), router.push("/login"))}
                  >
                    Log in
                  </Button>
                  <Button
                    className="w-full cursor-pointer bg-gradient-to-r from-(--chart-1) to-(--chart-2)"
                    onClick={() => (setIsMobileMenuOpen(false), router.push("/signup"))}
                  >
                    Sign up
                  </Button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      )}
    </motion.nav>
  )
}

export default Navbar
