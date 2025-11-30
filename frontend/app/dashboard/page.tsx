"use client"

import dynamic from "next/dynamic"

const Dashboard = dynamic(() => import("@/components/dashboard/dashboard"), { ssr: false })

export default function Page() {
  return <Dashboard />
}
