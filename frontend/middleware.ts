import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

// Define routes that require authentication
const protectedRoutes = [
  '/dashboard',
  '/created',
  '/joined',
  '/classroom',
]

// Define public routes that authenticated users shouldn't access
const authRoutes = ['/login', '/signup']

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl
  const method = request.method

  // Log every page navigation to the Next.js terminal
  console.log(`[NAV] ${new Date().toISOString()} ${method} ${pathname}`)

  // Allow public routes (no auth needed)
  if (pathname === '/' || pathname.startsWith('/_next') || pathname.startsWith('/api')) {
    return NextResponse.next()
  }

  // For protected routes, let the client-side handle authentication
  // since we're using localStorage for tokens
  return NextResponse.next()
}

// Configure which routes to run middleware on
export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - api (API routes)
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     * - public files (public folder)
     */
    '/((?!api|_next/static|_next/image|favicon.ico|.*\\..*|images).*)',
  ],
}
