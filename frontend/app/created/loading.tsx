import { LoadingOverlay } from "@/components/ui/liquid-orb-loader"

export default function Loading() {
  return (
    <div className="min-h-screen w-screen bg-background flex items-center justify-center">
      <LoadingOverlay 
        isLoading={true} 
        progress={0}
        message="Loading classrooms..."
        size="xl"
        fullScreen={true}
      />
    </div>
  )
}

