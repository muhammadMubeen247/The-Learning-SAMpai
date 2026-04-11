import { Skeleton } from "@/components/ui/skeleton"

export default function TopicLoading() {
  return (
    <div className="min-h-screen">
      <Skeleton className="h-16 w-full" />
      <div className="p-8 space-y-6">
        <Skeleton className="h-10 w-96" />
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      </div>
    </div>
  )
}
