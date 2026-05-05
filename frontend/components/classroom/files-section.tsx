"use client"

import { useState, useEffect, useRef } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Upload, X, Loader2, Check, Trash2 } from "lucide-react"
import { useRouter } from "next/navigation"
import File from "@/components/backgrounds/file"
import Orb from "@/components/backgrounds/orb"
import API from "@/api/axios"
import { normalizeErrorDetail } from "@/lib/error-utils"
import { useTheme } from "@/hooks/use-theme"
import { LoadingOrb } from "@/components/ui/liquid-orb-loader"
type FileType = {
  id: number
  filename: string
  file_url: string
  file_key: string
  file_type: string | null
  file_size: number | null
  processing_status: string
  folder_id: number
  uploaded_at: string
  processed_at: string | null
}

type FilesSectionProps = {
  classroomId: number
  folderId: number
  isOwner: boolean
  onFileUploaded?: () => void
}

export default function FilesSection({ classroomId, folderId, isOwner, onFileUploaded }: FilesSectionProps) {
  const { theme } = useTheme()
  const router = useRouter()
  const [files, setFiles] = useState<FileType[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingProgress, setLoadingProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [showLoadingModal, setShowLoadingModal] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadedFileId, setUploadedFileId] = useState<number | null>(null)
  const [processingStatus, setProcessingStatus] = useState<"pending" | "processing" | "naive_ready" | "completed" | "failed">("pending")
  const [processingProgress, setProcessingProgress] = useState(0)
  const [uploadingFileName, setUploadingFileName] = useState("")
  const fileInputRef = useRef<HTMLInputElement>(null)
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null)
  // Track processing status and completion tick visibility per file
  const [fileProcessingStatus, setFileProcessingStatus] = useState<Map<number, "pending" | "processing" | "naive_ready" | "completed" | "failed">>(new Map())
  const [fileShowTick, setFileShowTick] = useState<Map<number, boolean>>(new Map())

  const fileColor = theme === "dark" ? "#93C5FD" : "#38BDF8"

  const fetchFiles = async () => {
    setLoading(true)
    setLoadingProgress(0)
    setError(null)
    
    // Simulate progress for better UX
    const progressInterval = setInterval(() => {
      setLoadingProgress((prev) => {
        if (prev >= 90) return prev
        return prev + Math.random() * 15
      })
    }, 100)
    
    try {
      setLoadingProgress(30)
      const res = await API.get<FileType[]>(`/files/folder/${folderId}`)
      setLoadingProgress(70)
      setFiles(res.data)
      
      // Track processing status for all files
      const statusMap = new Map<number, "pending" | "processing" | "completed" | "failed">()
      res.data.forEach((file) => {
        statusMap.set(file.id, file.processing_status as "pending" | "processing" | "naive_ready" | "completed" | "failed")
      })
      setFileProcessingStatus(statusMap)
      
      // Start polling for any files that are still processing (only if not already polling for a new upload)
      const processingFiles = res.data.filter(
        (file) =>
          file.processing_status === "pending" ||
          file.processing_status === "processing" ||
          file.processing_status === "naive_ready"
      )
      if (processingFiles.length > 0 && !uploadedFileId) {
        // Poll for all processing files
        const pollAll = async () => {
          const stillProcessing: number[] = []
          for (const file of processingFiles) {
            try {
              const statusRes = await API.get(`/files/${file.id}/status`)
              const status = statusRes.data.status
              setFileProcessingStatus((prev) => new Map(prev).set(file.id, status))
              
              if (status === "completed") {
                setFiles((prev) =>
                  prev.map((f) =>
                    f.id === file.id
                      ? { ...f, processing_status: "completed", processed_at: statusRes.data.processed_at }
                      : f
                  )
                )
                // Show tick
                setFileShowTick((prev) => new Map(prev).set(file.id, true))
                setTimeout(() => {
                  setFileShowTick((prev) => {
                    const newMap = new Map(prev)
                    newMap.delete(file.id)
                    return newMap
                  })
                }, 3000)
              } else if (status === "failed") {
                setFiles((prev) =>
                  prev.map((f) => (f.id === file.id ? { ...f, processing_status: "failed" } : f))
                )
              } else {
                stillProcessing.push(file.id)
              }
            } catch (err) {
              console.error(`Error polling file ${file.id}:`, err)
              stillProcessing.push(file.id)
            }
          }
          
          // Stop polling if no files are still processing
          if (stillProcessing.length === 0 && pollingIntervalRef.current && !uploadedFileId) {
            clearInterval(pollingIntervalRef.current)
            pollingIntervalRef.current = null
          }
        }
        
        // Clear any existing interval first
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current)
        }
        
        // Poll every 2 seconds
        pollingIntervalRef.current = setInterval(pollAll, 2000)
      }
    } catch (err: any) {
      if (err?.response?.status === 401) {
        if (typeof window !== "undefined") {
          localStorage.removeItem("token")
          localStorage.removeItem("user")
        }
        router.push("/login")
      } else {
        setError("Failed to load files")
      }
    } finally {
      clearInterval(progressInterval)
      setLoadingProgress(100)
      setLoading(false)
      setTimeout(() => setLoadingProgress(0), 500)
    }
  }

  const handleDeleteFile = async (fileId: number, filename: string) => {
    if (!isOwner) return

    if (typeof window !== "undefined") {
      const confirmed = window.confirm(
        `Are you sure you want to delete "${filename}"?\nThis will remove the file and its chat history permanently.`
      )
      if (!confirmed) return
    }

    try {
      await API.delete(`/files/${fileId}`)
      // Remove from local state and status maps
      setFiles((prev) => prev.filter((f) => f.id !== fileId))
      setFileProcessingStatus((prev) => {
        const next = new Map(prev)
        next.delete(fileId)
        return next
      })
      setFileShowTick((prev) => {
        const next = new Map(prev)
        next.delete(fileId)
        return next
      })
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setError(normalizeErrorDetail(detail, "Failed to delete file"))
    }
  }

  useEffect(() => {
    void fetchFiles()

    // Cleanup polling on unmount
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current)
        pollingIntervalRef.current = null
      }
    }
  }, [folderId])   // eslint-disable-line react-hooks/exhaustive-deps

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Validate file type - match backend allowed extensions
    const allowedExtensions = [".pdf", ".docx", ".pptx", ".txt"]
    const fileExtension = "." + file.name.split(".").pop()?.toLowerCase()
    if (!allowedExtensions.includes(fileExtension)) {
      setError(`File type not allowed. Supported types: ${allowedExtensions.join(", ")}`)
      if (fileInputRef.current) {
        fileInputRef.current.value = ""
      }
      return
    }

    setError(null)
    setUploadingFileName(file.name)
    setShowLoadingModal(true)
    setIsUploading(true)
    setUploadProgress(0)
    setProcessingProgress(0)
    setProcessingStatus("pending")

    // Small delay to ensure modal is visible before upload starts
    await new Promise((resolve) => setTimeout(resolve, 100))
    
    // Upload immediately
    await uploadFile(file)
  }

  const uploadFile = async (file: File) => {
    if (!folderId || !file) {
      setError("Invalid folder or file")
      setIsUploading(false)
      setShowLoadingModal(false)
      return
    }

    try {
      // Create FormData with the file - parameter name must match backend: "file"
      const formData = new FormData()
      formData.append("file", file)

      // Show initial progress
      setUploadProgress(5)

      const response = await API.post<FileType>(
        `/files/upload/${folderId}`,
        formData,
        {
          onUploadProgress: (progressEvent: { loaded: number; total?: number }) => {
            if (progressEvent.total) {
              // Calculate progress up to 90% (remaining 10% for processing)
              const percentCompleted = Math.round((progressEvent.loaded * 90) / progressEvent.total)
              setUploadProgress(Math.max(5, Math.min(90, percentCompleted)))
            } else if (progressEvent.loaded > 0) {
              // If total is unknown, show indeterminate progress
              setUploadProgress(50)
            }
          },
        }
      )

      // Upload complete
      setUploadProgress(100)
      setUploadedFileId(response.data.id)
      setProcessingStatus("pending")
      setProcessingProgress(20)
      setIsUploading(false)

      // Add file to list immediately with low opacity
      const newFile: FileType = {
        ...response.data,
        processing_status: "pending",
      }
      setFiles((prev) => [...prev, newFile])
      setFileProcessingStatus((prev) => new Map(prev).set(response.data.id, "pending"))

      // Close upload modal after a short delay
      setTimeout(() => {
        setShowLoadingModal(false)
        setUploadProgress(0)
        setUploadingFileName("")
        if (fileInputRef.current) {
          fileInputRef.current.value = ""
        }
      }, 500)

      // Start polling for processing status
      // The useEffect will handle the polling
    } catch (err: any) {
      setIsUploading(false)
      setUploadProgress(0)
      setProcessingProgress(0)

      if (err?.response?.status === 401) {
        if (typeof window !== "undefined") {
          localStorage.removeItem("token")
          localStorage.removeItem("user")
        }
        router.push("/login")
      } else {
        const detail = err?.response?.data?.detail || err?.message || "Unknown error"
        setError(normalizeErrorDetail(detail, "Failed to upload file"))
        setShowLoadingModal(false)
        setUploadingFileName("")
        if (fileInputRef.current) {
          fileInputRef.current.value = ""
        }
      }
    }
  }

  useEffect(() => {
    if (!uploadedFileId) return

    const pollProcessingStatus = async (fileId: number) => {
      try {
        const res = await API.get(`/files/${fileId}/status`)
        const status = res.data.status
        setProcessingStatus(status)
        
        // Update file processing status
        setFileProcessingStatus((prev) => new Map(prev).set(fileId, status))

        // Update progress based on status
        if (status === "pending") {
          setProcessingProgress(20)
        } else if (status === "processing") {
          setProcessingProgress(50)
        } else if (status === "naive_ready") {
          // Phase 1 done — chat/flashcards usable; Phase 2 (KG) still running in background
          setProcessingProgress(70)
        } else if (status === "completed") {
          setProcessingProgress(100)
          // Stop polling
          if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current)
            pollingIntervalRef.current = null
          }
          
          // Update file in list with full opacity
          setFiles((prev) =>
            prev.map((file) =>
              file.id === fileId
                ? { ...file, processing_status: "completed", processed_at: res.data.processed_at }
                : file
            )
          )
          
          // Show green tick
          setFileShowTick((prev) => new Map(prev).set(fileId, true))
          
          // Hide tick after 3 seconds
          setTimeout(() => {
            setFileShowTick((prev) => {
              const newMap = new Map(prev)
              newMap.delete(fileId)
              return newMap
            })
          }, 3000)
          
          // Reset upload state
          setUploadedFileId(null)
          setProcessingStatus("pending")
          onFileUploaded?.()
        } else if (status === "failed") {
          setProcessingProgress(0)
          setError("File processing failed. Please try again.")
          if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current)
            pollingIntervalRef.current = null
          }
          // Update file status
          setFiles((prev) =>
            prev.map((file) =>
              file.id === fileId ? { ...file, processing_status: "failed" } : file
            )
          )
        }
      } catch (err: any) {
        console.error("Error polling processing status:", err)
        // Continue polling even if there's an error
      }
    }

    if (processingStatus !== "completed" && processingStatus !== "failed") {
      // Poll every 2 seconds
      const intervalId = setInterval(() => {
        pollProcessingStatus(uploadedFileId)
      }, 2000)
      pollingIntervalRef.current = intervalId

      return () => {
        if (intervalId) {
          clearInterval(intervalId)
        }
      }
    } else if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uploadedFileId, processingStatus])


  const hasFiles = files.length > 0
  const showUploadButton = isOwner

  return (
    <div className="p-4 sm:p-6 md:p-8 pt-36 sm:pt-40 min-h-full w-full overflow-x-hidden">
      <div className="max-w-[1400px] mx-auto w-full">
        {loading ? (
          <div className="flex items-center justify-center py-16 min-h-[60vh]">
            <LoadingOrb 
              progress={loadingProgress}
              size="lg"
              message="Loading files..."
              showProgress={true}
            />
          </div>
        ) : !hasFiles && !showUploadButton ? (
          <div className="text-center py-16">
            <p className="text-muted-foreground">No files yet</p>
          </div>
        ) : !hasFiles && showUploadButton ? (
          // Center the upload button when no files exist
          <div className="flex items-center justify-center min-h-[60vh]">
            <div className="group flex flex-col items-center gap-6">
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept=".pdf,.docx,.pptx,.txt"
                onChange={handleFileSelect}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="relative size-[160px] rounded-full cursor-pointer"
                aria-label="Upload file"
              >
                <Orb hue={300} rotateOnHover hoverIntensity={0.6} />
                <div className="pointer-events-none absolute inset-0 grid place-items-center">
                  <Upload className="size-12 text-foreground/95" />
                </div>
              </button>
              <p className="text-lg text-foreground text-center font-semibold tracking-wide">Upload File</p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 sm:gap-x-8 md:gap-x-10 gap-y-20 sm:gap-y-24">
            {/* Files */}
            {files.map((file) => {
              const fileStatus = fileProcessingStatus.get(file.id) || file.processing_status
              const isProcessing = fileStatus === "pending" || fileStatus === "processing"
              const showTick = fileShowTick.get(file.id) || false
              const opacity = isProcessing ? 0.4 : 1

              return (
                <div
                  key={file.id}
                  className="group flex flex-col items-center transition-opacity duration-300 cursor-pointer"
                  style={{ opacity }}
                  onClick={() => {
                    router.push(`/classroom/${classroomId}/folder/${folderId}/file/${file.id}`)
                  }}
                >
                  <div className="relative flex items-center justify-center w-full h-[150px] mb-2 overflow-visible">
                    <div className="absolute inset-0 blur-2xl bg-gradient-to-br from-chart-1/30 to-chart-2/30 rounded-full pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity" />
                    <div className="relative z-10 flex items-center justify-center">
                      <File color={fileColor} size={1.4} className="cursor-pointer transition-transform" />
                    </div>
                  </div>
                  <div className="flex flex-col items-center gap-1">
                    <p className="text-sm text-foreground text-center font-semibold tracking-wide leading-tight px-2 line-clamp-2 min-h-[2.5rem] flex items-center justify-center mt-1">
                      {file.filename}
                    </p>
                    {/* Tiny loading/tick indicator */}
                    {isProcessing && (
                      <div className="flex items-center justify-center h-3">
                        <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                      </div>
                    )}
                    {showTick && (
                      <div className="flex items-center justify-center h-3">
                        <div className="h-3 w-3 rounded-full bg-green-500 flex items-center justify-center">
                          <Check className="h-2 w-2 text-white" />
                        </div>
                      </div>
                    )}
                    {/* Delete icon under file name (owners only) */}
                    {isOwner && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          void handleDeleteFile(file.id, file.filename)
                        }}
                        className="mt-1 inline-flex items-center justify-center rounded-full border border-border/80 bg-card/80 px-3 py-1.5 text-sm text-destructive hover:bg-card/95 cursor-pointer"
                        aria-label={`Delete ${file.filename}`}
                      >
                        <Trash2 className="h-4.5 w-4.5" />
                      </button>
                    )}

                  </div>
                </div>
              )
            })}

            {/* Upload Button (Owner Only) - Positioned after files in grid */}
            {showUploadButton && (
              <div className="group flex flex-col items-center">
                <div className="relative flex items-center justify-center w-full h-[150px] mb-2">
                  <input
                    ref={fileInputRef}
                    type="file"
                    className="hidden"
                    accept=".pdf,.docx,.pptx,.txt"
                    onChange={handleFileSelect}
                  />
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="relative size-[110px] rounded-full cursor-pointer"
                    aria-label="Upload file"
                  >
                    <Orb hue={300} rotateOnHover hoverIntensity={0.6} />
                    <div className="pointer-events-none absolute inset-0 grid place-items-center">
                      <Upload className="size-7 text-foreground/95" />
                    </div>
                  </button>
                </div>
                <p className="text-sm text-foreground text-center font-semibold tracking-wide leading-tight px-2 min-h-[2.5rem] flex items-center justify-center mt-1">
                  Upload File
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Loading Modal */}
      <AnimatePresence>
        {showLoadingModal && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="fixed inset-0 z-30 bg-background/50 backdrop-blur-md"
              aria-hidden
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8 }}
              transition={{ type: "spring", stiffness: 260, damping: 22 }}
              className="fixed inset-0 z-40 grid place-items-center p-4"
              role="dialog"
              aria-modal="true"
            >
              <div className="relative w-full max-w-md rounded-2xl border border-border bg-card/70 backdrop-blur-xl shadow-2xl">
                <div className="relative p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-medium text-foreground">Uploading File</h3>
                    {uploadProgress >= 100 && (
                      <button
                        type="button"
                        onClick={() => {
                          setShowLoadingModal(false)
                          setUploadProgress(0)
                          setUploadingFileName("")
                        }}
                        className="p-2 rounded-md border border-border/60 bg-card/60 hover:bg-card/80 cursor-pointer"
                        aria-label="Close"
                      >
                        <X className="size-4" />
                      </button>
                    )}
                  </div>

                  <div className="space-y-4">
                    {uploadingFileName && (
                      <div className="space-y-2">
                        <label className="text-sm text-muted-foreground">File</label>
                        <div className="w-full rounded-md border border-border bg-background/60 px-3 py-2 text-foreground">
                          {uploadingFileName}
                        </div>
                      </div>
                    )}

                    {/* Upload Progress */}
                    <div className="space-y-3 pt-2">
                      {uploadProgress < 100 && (
                        <div className="flex flex-col items-center justify-center py-4">
                          <LoadingOrb 
                            progress={uploadProgress}
                            size="md"
                            message="Uploading file..."
                            showProgress={true}
                          />
                        </div>
                      )}
                      {uploadProgress >= 100 && processingStatus === "pending" && (
                        <div className="flex flex-col items-center justify-center py-4 space-y-2">
                          <div className="flex items-center gap-2 text-sm text-green-500">
                            <span>✓ File uploaded successfully!</span>
                          </div>
                          <LoadingOrb 
                            progress={processingProgress}
                            size="sm"
                            message="Processing file..."
                            showProgress={true}
                          />
                        </div>
                      )}
                      {uploadProgress >= 100 && processingStatus === "processing" && (
                        <div className="flex flex-col items-center justify-center py-4 space-y-2">
                          <div className="flex items-center gap-2 text-sm text-green-500">
                            <span>✓ File uploaded successfully!</span>
                          </div>
                          <LoadingOrb
                            progress={processingProgress}
                            size="sm"
                            message="Processing file..."
                            showProgress={true}
                          />
                        </div>
                      )}
                      {uploadProgress >= 100 && processingStatus === "naive_ready" && (
                        <div className="flex flex-col items-center justify-center py-4 space-y-2">
                          <div className="flex items-center gap-2 text-sm text-green-500">
                            <span>✓ Chat ready! Full analysis still loading...</span>
                          </div>
                          <LoadingOrb
                            progress={processingProgress}
                            size="sm"
                            message="Building knowledge graph..."
                            showProgress={true}
                          />
                        </div>
                      )}
                      {uploadProgress >= 100 && processingStatus === "completed" && (
                        <div className="flex items-center justify-center gap-2 text-sm text-green-500 py-4">
                          <span>✓ File uploaded and processed successfully!</span>
                        </div>
                      )}
                    </div>

                    {error && <p className="text-sm text-destructive/90">{error}</p>}

                    {uploadProgress < 100 && (
                      <div className="flex items-center justify-end gap-3 pt-2">
                        <button
                          type="button"
                          onClick={() => {
                            if (pollingIntervalRef.current) {
                              clearInterval(pollingIntervalRef.current)
                              pollingIntervalRef.current = null
                            }
                            setShowLoadingModal(false)
                            setUploadProgress(0)
                            setProcessingProgress(0)
                            setUploadedFileId(null)
                            setProcessingStatus("pending")
                            setUploadingFileName("")
                            if (fileInputRef.current) {
                              fileInputRef.current.value = ""
                            }
                          }}
                          className="px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer"
                          disabled={isUploading}
                        >
                          Cancel
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}

