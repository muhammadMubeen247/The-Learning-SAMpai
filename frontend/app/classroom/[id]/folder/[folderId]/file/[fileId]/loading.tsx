import { Skeleton } from "@/components/ui/skeleton"

export default function FileLoading() {
  return (
    <div className="min-h-screen">
      <Skeleton className="h-16 w-full" />
      <div className="p-8 space-y-6">
        <Skeleton className="h-10 w-96" />
        <div className="grid gap-6 md:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
      </div>
    </div>
  )
}
