import { Skeleton } from "@/components/ui/skeleton"

export default function FolderLoading() {
  return (
    <div className="min-h-screen">
      <Skeleton className="h-16 w-full" />
      <div className="p-8 space-y-6">
        <Skeleton className="h-10 w-64" />
        <div className="space-y-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      </div>
    </div>
  )
}
