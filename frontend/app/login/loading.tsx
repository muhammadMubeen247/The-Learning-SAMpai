import { Skeleton } from "@/components/ui/skeleton"

export default function LoginLoading() {
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Skeleton className="h-[600px] w-full max-w-md" />
    </div>
  )
}
