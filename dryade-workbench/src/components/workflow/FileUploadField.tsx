// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useCallback, useState } from "react";
import { Upload, X, FileIcon, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface FileUploadFieldProps {
  id: string;
  value: File | null;
  onChange: (file: File | null) => void;
  accept?: string;
  maxSizeMB?: number;
  disabled?: boolean;
  error?: boolean;
}

const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

export const FileUploadField = ({
  id,
  value,
  onChange,
  accept,
  maxSizeMB = 50,
  disabled = false,
  error = false,
}: FileUploadFieldProps) => {
  const [isDragActive, setIsDragActive] = useState(false);
  const [sizeError, setSizeError] = useState<string | null>(null);

  const maxSizeBytes = maxSizeMB * 1024 * 1024;

  const handleFile = useCallback(
    (file: File | null) => {
      setSizeError(null);
      if (file && file.size > maxSizeBytes) {
        setSizeError(`File exceeds ${maxSizeMB}MB limit`);
        return;
      }
      onChange(file);
    },
    [maxSizeBytes, maxSizeMB, onChange]
  );

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragActive(false);

      if (disabled) return;

      const files = e.dataTransfer.files;
      if (files && files.length > 0) {
        handleFile(files[0]);
      }
    },
    [disabled, handleFile]
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (files && files.length > 0) {
        handleFile(files[0]);
      }
    },
    [handleFile]
  );

  const handleClear = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      handleFile(null);
    },
    [handleFile]
  );

  if (value) {
    return (
      <div
        className={cn(
          "flex items-center gap-3 p-3 rounded-lg border bg-secondary/30",
          error && "border-destructive",
          !error && "border-border"
        )}
      >
        <FileIcon className="h-8 w-8 text-muted-foreground flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{value.name}</p>
          <p className="text-xs text-muted-foreground">
            {formatFileSize(value.size)}
          </p>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 flex-shrink-0"
          onClick={handleClear}
          disabled={disabled}
        >
          <X className="h-4 w-4" />
          <span className="sr-only">Remove file</span>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        className={cn(
          "relative flex flex-col items-center justify-center gap-2 p-6 rounded-lg border-2 border-dashed transition-colors cursor-pointer",
          isDragActive && "border-primary bg-primary/5",
          !isDragActive && !error && "border-muted-foreground/25 hover:border-muted-foreground/50",
          error && "border-destructive",
          disabled && "opacity-50 cursor-not-allowed"
        )}
      >
        <input
          id={id}
          type="file"
          accept={accept}
          onChange={handleInputChange}
          disabled={disabled}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
        />
        <Upload
          className={cn(
            "h-8 w-8",
            isDragActive ? "text-primary" : "text-muted-foreground"
          )}
        />
        <div className="text-center">
          <p className="text-sm font-medium">
            {isDragActive ? "Drop file here" : "Drop file or click to browse"}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Max size: {maxSizeMB}MB
          </p>
        </div>
      </div>
      {sizeError && (
        <div className="flex items-center gap-1 text-destructive text-xs">
          <AlertCircle className="h-3 w-3" />
          <span>{sizeError}</span>
        </div>
      )}
    </div>
  );
};

export default FileUploadField;
