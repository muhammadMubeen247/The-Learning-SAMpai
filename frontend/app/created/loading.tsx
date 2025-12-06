import { Skeleton } from "@/components/ui/skeleton"

export default function CreatedLoading() {
  return (
    <div className="min-h-screen p-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <Skeleton className="h-10 w-64" />
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Skeleton key={i} className="h-48 w-full" />
          ))}
        </div>
      </div>
    </div>
  )
}
