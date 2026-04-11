import type React from "react"
import type { Metadata } from "next"
import { Geist, Geist_Mono } from "next/font/google"
import { Providers } from "./providers"
import "./globals.css"

const geistSans = Geist({ 
  subsets: ["latin"], 
  variable: "--font-geist-sans",
  display: "swap",
})
const geistMono = Geist_Mono({ 
  subsets: ["latin"], 
  variable: "--font-geist-mono",
  display: "swap",
})

export const metadata: Metadata = {
  title: {
    default: "The Learning SAMpai - AI-Powered Learning Platform",
    template: "%s | The Learning SAMpai"
  },
  description: "Transform your learning experience with AI-powered classrooms, intelligent document processing, and personalized topic extraction.",
  keywords: ["learning", "AI", "education", "SAMpai", "online learning", "classroom management"],
  authors: [{ name: "The Learning SAMpai Team" }],
  openGraph: {
    type: "website",
    locale: "en_US",
    url: "https://learningsampai.com",
    title: "The Learning SAMpai - AI-Powered Learning Platform",
    description: "Transform your learning experience with AI-powered classrooms",
    siteName: "The Learning SAMpai",
  },
  twitter: {
    card: "summary_large_image",
    title: "The Learning SAMpai",
    description: "AI-Powered Learning Platform",
  },
  robots: {
    index: true,
    follow: true,
  },
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} antialiased scroll-smooth`}
    >
      <head>
        {/* Preconnect to external domains for faster loading */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        
        {/* Theme script to prevent flash */}
        <script
          dangerouslySetInnerHTML={{
            __html: `
(function(){
  try {
    var t = localStorage.getItem('theme');
    if (!t) { t = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'; }
    if (t === 'dark') document.documentElement.classList.add('dark');
    else document.documentElement.classList.remove('dark');
  } catch (e) {}
})();`,
          }}
        />
      </head>
      <body className="font-sans">
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  )
}
