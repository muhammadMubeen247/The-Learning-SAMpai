import { Skeleton } from "@/components/ui/skeleton"

export default function ClassroomLoading() {
  return (
    <div className="min-h-screen">
      <Skeleton className="h-16 w-full" />
      <div className="p-8 space-y-6">
        <Skeleton className="h-10 w-48" />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
      </div>
    </div>
  )
}
