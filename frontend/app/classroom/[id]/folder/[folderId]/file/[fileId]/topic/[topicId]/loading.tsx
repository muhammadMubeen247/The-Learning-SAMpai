import { Skeleton } from "@/components/ui/skeleton"

export default function TopicLoading() {
  return (
    <div className="min-h-screen">
      <Skeleton className="h-16 w-full" />
      <div className="p-8 space-y-6">
        <Skeleton className="h-12 w-full max-w-2xl" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    </div>
  )
}
