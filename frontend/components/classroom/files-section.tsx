"use client"

import { useState, useEffect, useRef } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Upload, X, Loader2 } from "lucide-react"
import File from "@/components/backgrounds/file"
import Orb from "@/components/backgrounds/orb"
import API from "@/api/axios"
import { normalizeErrorDetail } from "@/lib/error-utils"
import { useTheme } from "@/hooks/use-theme"
import LiquidProgress from "@/components/ui/liquid-progress"

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
  folderId: number
  isOwner: boolean
  onFileUploaded?: () => void
}

export default function FilesSection({ folderId, isOwner, onFileUploaded }: FilesSectionProps) {
  const { theme } = useTheme()
  const [files, setFiles] = useState<FileType[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showLoadingModal, setShowLoadingModal] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadedFileId, setUploadedFileId] = useState<number | null>(null)
  const [processingStatus, setProcessingStatus] = useState<"pending" | "processing" | "completed" | "failed">("pending")
  const [processingProgress, setProcessingProgress] = useState(0)
  const [uploadingFileName, setUploadingFileName] = useState("")
  const fileInputRef = useRef<HTMLInputElement>(null)
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null)

  const fileColor = theme === "dark" ? "#93C5FD" : "#38BDF8"

  const fetchFiles = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await API.get<FileType[]>(`/files/folder/${folderId}`)
      setFiles(res.data)
    } catch (err: any) {
      if (err?.response?.status === 401) {
        if (typeof window !== "undefined") {
          localStorage.removeItem("token")
          localStorage.removeItem("user")
        }
        window.location.href = "/login"
      } else {
        setError("Failed to load files")
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void fetchFiles()
  }, [folderId])

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
        window.location.href = "/login"
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

        // Update progress based on status
        if (status === "pending") {
          setProcessingProgress(20)
        } else if (status === "processing") {
          setProcessingProgress(60)
        } else if (status === "completed") {
          setProcessingProgress(100)
          // Stop polling and refresh files
          if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current)
            pollingIntervalRef.current = null
          }
          // Refresh files list
          const filesRes = await API.get<FileType[]>(`/files/folder/${folderId}`)
          setFiles(filesRes.data)
          onFileUploaded?.()
          // Close modal after a short delay
          setTimeout(() => {
            setShowLoadingModal(false)
            setUploadProgress(0)
            setProcessingProgress(0)
            setUploadedFileId(null)
            setProcessingStatus("pending")
            setUploadingFileName("")
            if (fileInputRef.current) {
              fileInputRef.current.value = ""
            }
          }, 1500)
        } else if (status === "failed") {
          setProcessingProgress(0)
          setError("File processing failed. Please try again.")
          if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current)
            pollingIntervalRef.current = null
          }
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
          <div className="text-center py-16">
            <p className="text-muted-foreground">Loading files...</p>
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
            {files.map((file) => (
              <div key={file.id} className="group flex flex-col items-center">
                <div className="relative flex items-center justify-center w-full h-[150px] mb-2 overflow-visible">
                  <div className="absolute inset-0 blur-2xl bg-gradient-to-br from-chart-1/30 to-chart-2/30 rounded-full pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity" />
                  <div className="relative z-10 flex items-center justify-center">
                    <File color={fileColor} size={1.4} className="cursor-pointer transition-transform" />
                  </div>
                </div>
                <p className="text-sm text-foreground text-center font-semibold tracking-wide leading-tight px-2 line-clamp-2 min-h-[2.5rem] flex items-center justify-center mt-1">
                  {file.filename}
                </p>
              </div>
            ))}

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
                    {processingStatus === "completed" && (
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
                        <LiquidProgress progress={uploadProgress} label="Uploading file..." />
                      )}
                      {uploadProgress >= 100 && processingProgress < 100 && (
                        <div className="space-y-2">
                          <LiquidProgress progress={processingProgress} label="Processing file..." />
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <Loader2 className="size-3 animate-spin" />
                            <span>
                              {processingStatus === "pending" && "Preparing..."}
                              {processingStatus === "processing" &&
                                "Extracting text and generating embeddings..."}
                              {processingStatus === "completed" && "Complete!"}
                            </span>
                          </div>
                        </div>
                      )}
                      {uploadProgress >= 100 && processingProgress >= 100 && (
                        <div className="flex items-center gap-2 text-sm text-green-500">
                          <span>✓ File uploaded and processed successfully!</span>
                        </div>
                      )}
                    </div>

                    {error && <p className="text-sm text-destructive/90">{error}</p>}

                    {processingStatus !== "completed" && uploadProgress < 100 && (
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

