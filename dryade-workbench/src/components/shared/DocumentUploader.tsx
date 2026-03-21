// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// DocumentUploader - Drag-and-drop file upload with 4-stage progress
// Based on COMPONENTS-4.md specification

import { useState, useRef, useCallback } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Upload, FileText, File, Loader2, CheckCircle2, AlertCircle, X } from "lucide-react";

type UploadStage = "idle" | "uploading" | "chunking" | "embedding" | "indexing" | "complete" | "error";

interface UploadProgress {
  percent: number;
  stage: UploadStage;
  stageLabel: string;
}

interface DocumentUploaderProps {
  acceptedTypes?: string[];
  maxSize?: number; // bytes
  onUpload: (file: File, metadata?: Record<string, unknown>) => Promise<{ source_id: string }>;
  onProgress?: (progress: UploadProgress) => void;
  onError?: (error: Error) => void;
  onComplete?: (sourceId: string) => void;
  disabled?: boolean;
  className?: string;
}

const stageLabels: Record<UploadStage, string> = {
  idle: "Ready to upload",
  uploading: "Uploading...",
  chunking: "Splitting into chunks...",
  embedding: "Generating embeddings...",
  indexing: "Indexing in database...",
  complete: "Complete!",
  error: "Upload failed",
};

const stageOrder: UploadStage[] = ["uploading", "chunking", "embedding", "indexing"];

const DocumentUploader = ({
  acceptedTypes = [".pdf", ".txt", ".md", ".docx"],
  maxSize = 100 * 1024 * 1024, // 100MB
  onUpload,
  onProgress,
  onError,
  onComplete,
  disabled = false,
  className,
}: DocumentUploaderProps) => {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (!disabled) setIsDragging(true);
  }, [disabled]);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const validateFile = (file: File): string | null => {
    if (file.size > maxSize) {
      return `File too large. Maximum size is ${Math.round(maxSize / (1024 * 1024))}MB`;
    }
    const ext = `.${file.name.split(".").pop()?.toLowerCase()}`;
    if (!acceptedTypes.includes(ext)) {
      return `Invalid file type. Accepted: ${acceptedTypes.join(", ")}`;
    }
    return null;
  };

  const simulateProgress = async (file: File) => {
    setError(null);
    
    for (let i = 0; i < stageOrder.length; i++) {
      const stage = stageOrder[i];
      const progress: UploadProgress = {
        percent: ((i + 1) / stageOrder.length) * 100,
        stage,
        stageLabel: stageLabels[stage],
      };
      setUploadProgress(progress);
      onProgress?.(progress);
      await new Promise((resolve) => setTimeout(resolve, 800));
    }
  };

  const handleUpload = async (file: File) => {
    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      onError?.(new Error(validationError));
      return;
    }

    setSelectedFile(file);
    setUploadProgress({ percent: 0, stage: "uploading", stageLabel: stageLabels.uploading });

    try {
      // Simulate progress stages
      await simulateProgress(file);

      // Actual upload
      const result = await onUpload(file);
      
      setUploadProgress({ percent: 100, stage: "complete", stageLabel: stageLabels.complete });
      onComplete?.(result.source_id);
      
      // Reset after delay
      setTimeout(() => {
        setSelectedFile(null);
        setUploadProgress(null);
      }, 2000);
    } catch (err) {
      const error = err instanceof Error ? err : new Error("Upload failed");
      setError(error.message);
      setUploadProgress({ percent: 0, stage: "error", stageLabel: error.message });
      onError?.(error);
    }
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    
    if (disabled) return;
    
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  }, [disabled]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleUpload(file);
    // Reset input
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleCancel = () => {
    setSelectedFile(null);
    setUploadProgress(null);
    setError(null);
  };

  const getFileIcon = (filename: string) => {
    const ext = filename.split(".").pop()?.toLowerCase();
    if (ext === "pdf") return <FileText className="w-8 h-8 text-red-500" />;
    if (ext === "md") return <File className="w-8 h-8 text-purple-500" />;
    if (ext === "docx") return <File className="w-8 h-8 text-blue-500" />;
    return <File className="w-8 h-8 text-muted-foreground" />;
  };

  const isUploading = uploadProgress && uploadProgress.stage !== "idle" && uploadProgress.stage !== "complete" && uploadProgress.stage !== "error";

  return (
    <div
      className={cn(
        "relative border-2 border-dashed rounded-xl transition-all duration-200",
        isDragging && !disabled && "border-primary bg-primary/5",
        !isDragging && !disabled && "border-border hover:border-primary/50",
        disabled && "opacity-50 cursor-not-allowed border-muted",
        className
      )}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept={acceptedTypes.join(",")}
        onChange={handleFileSelect}
        disabled={disabled || isUploading}
        className="hidden"
        aria-label="File upload input"
      />

      <div className="p-8 flex flex-col items-center justify-center gap-4 min-h-[200px]">
        {/* Uploading State */}
        {uploadProgress && uploadProgress.stage !== "idle" ? (
          <div className="w-full max-w-xs space-y-4">
            {/* File Info */}
            {selectedFile && (
              <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
                {getFileIcon(selectedFile.name)}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{selectedFile.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {(selectedFile.size / 1024).toFixed(1)} KB
                  </p>
                </div>
                {uploadProgress.stage !== "complete" && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    onClick={handleCancel}
                    aria-label="Cancel upload"
                  >
                    <X className="w-4 h-4" />
                  </Button>
                )}
              </div>
            )}

            {/* Progress */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-2">
                  {uploadProgress.stage === "complete" ? (
                    <CheckCircle2 className="w-4 h-4 text-success" />
                  ) : uploadProgress.stage === "error" ? (
                    <AlertCircle className="w-4 h-4 text-destructive" />
                  ) : (
                    <Loader2 className="w-4 h-4 animate-spin text-primary" />
                  )}
                  <span>{uploadProgress.stageLabel}</span>
                </span>
                <span className="text-muted-foreground">{Math.round(uploadProgress.percent)}%</span>
              </div>
              <Progress value={uploadProgress.percent} className="h-2" />
            </div>

            {/* Stage Indicators */}
            <div className="flex justify-center gap-2">
              {stageOrder.map((stage, idx) => {
                const currentIdx = stageOrder.indexOf(uploadProgress.stage as typeof stageOrder[number]);
                const isComplete = idx < currentIdx || uploadProgress.stage === "complete";
                const isCurrent = stage === uploadProgress.stage;
                
                return (
                  <div
                    key={stage}
                    className={cn(
                      "w-2 h-2 rounded-full transition-colors",
                      isComplete && "bg-success",
                      isCurrent && "bg-primary animate-pulse",
                      !isComplete && !isCurrent && "bg-muted"
                    )}
                    title={stageLabels[stage]}
                  />
                );
              })}
            </div>

            {/* Error */}
            {error && (
              <p className="text-sm text-destructive text-center">{error}</p>
            )}
          </div>
        ) : (
          /* Idle State */
          <>
            <div
              className={cn(
                "w-16 h-16 rounded-full flex items-center justify-center transition-colors",
                isDragging ? "bg-primary/20" : "bg-muted"
              )}
            >
              <Upload
                className={cn(
                  "w-8 h-8 transition-colors",
                  isDragging ? "text-primary" : "text-muted-foreground"
                )}
              />
            </div>
            
            <div className="text-center space-y-1">
              <p className="text-foreground font-medium">
                {isDragging ? "Drop file here" : "Drag & drop files here"}
              </p>
              <p className="text-sm text-muted-foreground">
                or click to browse
              </p>
            </div>

            <Button
              variant="outline"
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled}
            >
              Browse Files
            </Button>

            <p className="text-xs text-muted-foreground text-center">
              Supports {acceptedTypes.join(", ")} up to {Math.round(maxSize / (1024 * 1024))}MB
            </p>
          </>
        )}
      </div>
    </div>
  );
};

export default DocumentUploader;
