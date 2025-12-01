"use client"

import { useEffect, useState, useRef } from "react"
import { usePathname, useRouter } from "next/navigation"
import { LoadingOverlay } from "./liquid-orb-loader"

/**
 * NavigationLoader - Shows loading orb during Next.js page transitions
 * Intercepts all navigation events (clicks, router.push, etc.) to show loading immediately
 */
export function NavigationLoader() {
  const pathname = usePathname()
  const router = useRouter()
  const [isNavigating, setIsNavigating] = useState(false)
  const [loadingProgress, setLoadingProgress] = useState(0)
  const previousPathname = useRef<string>(pathname)
  const progressIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const hideTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const readyCheckIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const maxWaitTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  // Function to start loading
  const startLoading = () => {
    setIsNavigating(true)
    setLoadingProgress(0)

    // Clear any existing timers
    if (progressIntervalRef.current) {
      clearInterval(progressIntervalRef.current)
    }
    if (hideTimeoutRef.current) {
      clearTimeout(hideTimeoutRef.current)
    }
    if (readyCheckIntervalRef.current) {
      clearInterval(readyCheckIntervalRef.current)
    }
    if (maxWaitTimeoutRef.current) {
      clearTimeout(maxWaitTimeoutRef.current)
    }

    let currentProgress = 0

    // Simulate progress while page is compiling/loading
    progressIntervalRef.current = setInterval(() => {
      // Gradually increase progress, but cap at 95% until page is ready
      if (currentProgress >= 95) return
      // Faster progress initially, slower as we approach completion
      const increment = currentProgress < 50 ? 8 : currentProgress < 80 ? 5 : 2
      currentProgress = Math.min(95, currentProgress + Math.random() * increment)
      setLoadingProgress(currentProgress)
    }, 150)

    // Check if page is ready by monitoring DOM changes
    const checkPageReady = () => {
      // Wait a bit for initial render
      if (currentProgress < 30) return false
      
      // Check if main content is present
      const hasContent = document.querySelector('main') || 
                        document.querySelector('[role="main"]') ||
                        (document.body && document.body.children.length > 2)
      
      if (hasContent) {
        // Page seems ready, complete the loading
        if (progressIntervalRef.current) {
          clearInterval(progressIntervalRef.current)
        }
        if (readyCheckIntervalRef.current) {
          clearInterval(readyCheckIntervalRef.current)
        }
        if (maxWaitTimeoutRef.current) {
          clearTimeout(maxWaitTimeoutRef.current)
        }
        setLoadingProgress(100)
        
        // Hide after showing completion
        hideTimeoutRef.current = setTimeout(() => {
          setIsNavigating(false)
          setLoadingProgress(0)
        }, 400)
        return true
      }
      return false
    }

    // Poll for page readiness
    readyCheckIntervalRef.current = setInterval(() => {
      if (checkPageReady()) {
        if (readyCheckIntervalRef.current) {
          clearInterval(readyCheckIntervalRef.current)
        }
      }
    }, 200)

    // Fallback: Hide after maximum wait time (10 seconds)
    maxWaitTimeoutRef.current = setTimeout(() => {
      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current)
      }
      if (readyCheckIntervalRef.current) {
        clearInterval(readyCheckIntervalRef.current)
      }
      setLoadingProgress(100)
      hideTimeoutRef.current = setTimeout(() => {
        setIsNavigating(false)
        setLoadingProgress(0)
      }, 400)
    }, 10000)
  }

  // Intercept all link clicks and navigation events
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      
      // Find the closest anchor that might trigger navigation
      const link = target.closest('a[href]')
      
      if (link) {
        const href = link.getAttribute('href')
        
        // Only intercept internal navigation (starts with /)
        if (href && href.startsWith('/') && !href.startsWith('//')) {
          // Show loader immediately on click - BEFORE navigation starts
          startLoading()
          // Don't prevent default - let Next.js handle the navigation
          // The loader is already showing, so user sees immediate feedback
        }
      } else {
        // Check if it's a button that might trigger navigation
        // Look for buttons with cursor-pointer or navigation-related classes
        const button = target.closest('button')
        if (button) {
          const buttonText = button.textContent?.toLowerCase() || ''
          const hasNavigationIntent = 
            button.classList.contains('cursor-pointer') ||
            buttonText.includes('dashboard') ||
            buttonText.includes('home') ||
            buttonText.includes('back') ||
            buttonText.includes('next') ||
            button.getAttribute('onclick')?.includes('router.push') ||
            button.getAttribute('onclick')?.includes('router.replace')
          
          // If it looks like navigation, show loader
          // The actual navigation will be handled by the component's onClick
          if (hasNavigationIntent) {
            startLoading()
          }
        }
      }
    }

    // Listen to all clicks in capture phase to catch them early
    document.addEventListener('click', handleClick, true)

    // Listen to popstate for browser back/forward
    const handlePopState = () => {
      startLoading()
    }
    window.addEventListener("popstate", handlePopState)

    // Create a custom event that components can dispatch for router.push calls
    const handleNavigationStart = () => {
      startLoading()
    }
    window.addEventListener('navigation-start', handleNavigationStart as EventListener)

    // Also intercept pushState/replaceState calls
    const originalPushState = history.pushState
    const originalReplaceState = history.replaceState
    
    history.pushState = function(...args) {
      startLoading()
      return originalPushState.apply(history, args)
    }
    
    history.replaceState = function(...args) {
      startLoading()
      return originalReplaceState.apply(history, args)
    }

    return () => {
      document.removeEventListener('click', handleClick, true)
      window.removeEventListener("popstate", handlePopState)
      window.removeEventListener('navigation-start', handleNavigationStart as EventListener)
      history.pushState = originalPushState
      history.replaceState = originalReplaceState
    }
  }, [])

  // Also detect pathname changes as fallback
  useEffect(() => {
    // Only show loading if pathname actually changed
    if (pathname === previousPathname.current) return
    
    // If we're not already showing loading, start it
    if (!isNavigating) {
      startLoading()
    }
    
    previousPathname.current = pathname
  }, [pathname, isNavigating])

  return (
    <LoadingOverlay
      isLoading={isNavigating}
      progress={loadingProgress}
      message="Loading page..."
      size="xl"
      fullScreen={true}
    />
  )
}

