// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useCallback, useRef, useState } from "react";
import {
  Package,
  Upload,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertTriangle,
  ArrowRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { usePluginImport } from "@/hooks/usePluginImport";

interface PluginImportDropzoneProps {
  className?: string;
}

/**
 * Drag-and-drop zone for importing .dryadepkg marketplace packages.
 *
 * Visual states:
 *   idle       — dashed border, neutral
 *   drag-over  — blue border + blue background tint
 *   pending    — pulsing spinner + "Importing plugin..." text
 *   success    — green border + green check
 *   error      — red border + error message
 *   conflict   — modal overlay asking to confirm overwrite
 */
export function PluginImportDropzone({ className }: PluginImportDropzoneProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const {
    importFile,
    isPending,
    isSuccess,
    isError,
    error,
    reset,
    conflict,
    confirmOverwrite,
    cancelOverwrite,
  } = usePluginImport();

  const handleFile = useCallback(
    (file: File) => {
      importFile(file);
    },
    [importFile]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) {
        handleFile(file);
      }
    },
    [handleFile]
  );

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragOver(false);
    }
  }, []);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        handleFile(file);
      }
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    },
    [handleFile]
  );

  const handleChooseFile = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleReset = useCallback(() => {
    reset();
  }, [reset]);

  const isIdle = !isPending && !isSuccess && !isError && !conflict;

  const zoneClass = cn(
    "relative flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-8 transition-colors duration-200 bg-card/60 backdrop-blur-md",
    isDragOver && isIdle && "border-primary bg-primary/10",
    isPending && "border-muted-foreground/40 bg-muted/20 cursor-not-allowed",
    isSuccess && "border-success bg-success/5",
    isError && "border-destructive bg-destructive/5",
    conflict && "border-warning bg-warning/5",
    isIdle &&
      !isDragOver &&
      "border-muted-foreground/30 hover:border-muted-foreground/50 cursor-pointer"
  );

  return (
    <div className={cn("w-full", className)}>
      <div
        className={zoneClass}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={isIdle ? handleChooseFile : undefined}
        role={isIdle ? "button" : undefined}
        tabIndex={isIdle ? 0 : undefined}
        onKeyDown={
          isIdle
            ? (e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  handleChooseFile();
                }
              }
            : undefined
        }
        aria-label={
          isIdle ? "Drop .dryadepkg file here or click to browse" : undefined
        }
      >
        {/* Idle state */}
        {isIdle && (
          <>
            <div className="flex flex-col items-center gap-2 pointer-events-none">
              {isDragOver ? (
                <Upload className="w-10 h-10 text-primary" aria-hidden="true" />
              ) : (
                <Package
                  className="w-10 h-10 text-muted-foreground"
                  aria-hidden="true"
                />
              )}
              <p className="text-sm font-medium">
                {isDragOver ? "Release to import" : "Drop .dryadepkg file here"}
              </p>
              <p className="text-xs text-muted-foreground">or</p>
            </div>
            <button
              type="button"
              className="pointer-events-auto relative z-10 rounded-md border border-input bg-background px-4 py-2 text-sm font-medium shadow-sm hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={(e) => {
                e.stopPropagation();
                handleChooseFile();
              }}
            >
              Choose File
            </button>
          </>
        )}

        {/* Loading state */}
        {isPending && (
          <>
            <Loader2
              className="w-10 h-10 text-primary motion-safe:animate-spin"
              aria-hidden="true"
            />
            <p className="text-sm font-medium text-muted-foreground">
              Importing plugin...
            </p>
          </>
        )}

        {/* Success state */}
        {isSuccess && (
          <>
            <CheckCircle2
              className="w-10 h-10 text-success"
              aria-hidden="true"
            />
            <p className="text-sm font-medium text-success">
              Plugin imported successfully
            </p>
            <button
              type="button"
              className="text-xs text-muted-foreground underline hover:text-foreground"
              onClick={(e) => {
                e.stopPropagation();
                handleReset();
              }}
            >
              Import another
            </button>
          </>
        )}

        {/* Conflict state — version diff + confirm/cancel */}
        {conflict && (
          <div className="flex flex-col items-center gap-4 w-full max-w-sm">
            <AlertTriangle
              className="w-10 h-10 text-warning"
              aria-hidden="true"
            />
            <div className="text-center">
              <p className="text-sm font-semibold">
                Plugin already installed
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                <span className="font-medium">{conflict.pluginName}</span> is
                already installed. Replace it?
              </p>
            </div>

            {/* Version diff */}
            <div className="flex items-center gap-3 rounded-md bg-muted/50 px-4 py-2.5 text-sm w-full justify-center">
              <span className="font-mono text-destructive/80">
                v{conflict.existingVersion ?? "?"}
              </span>
              <ArrowRight className="w-4 h-4 text-muted-foreground shrink-0" />
              <span className="font-mono text-success">
                v{conflict.newVersion ?? "?"}
              </span>
            </div>

            <div className="flex gap-3 w-full">
              <button
                type="button"
                className="flex-1 rounded-md border border-input bg-background px-4 py-2 text-sm font-medium shadow-sm hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={(e) => {
                  e.stopPropagation();
                  cancelOverwrite();
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                className="flex-1 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm hover:bg-primary/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={(e) => {
                  e.stopPropagation();
                  confirmOverwrite();
                }}
              >
                Replace
              </button>
            </div>
          </div>
        )}

        {/* Error state */}
        {isError && (
          <>
            <XCircle
              className="w-10 h-10 text-destructive"
              aria-hidden="true"
            />
            <div className="text-center">
              <p className="text-sm font-medium text-destructive">
                Import failed
              </p>
              {error && (
                <p className="text-xs text-muted-foreground mt-1 max-w-xs">
                  {error.message}
                </p>
              )}
            </div>
            <button
              type="button"
              className="text-xs text-muted-foreground underline hover:text-foreground"
              onClick={(e) => {
                e.stopPropagation();
                handleReset();
              }}
            >
              Try again
            </button>
          </>
        )}

        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".dryadepkg"
          className="hidden"
          onChange={handleInputChange}
          aria-hidden="true"
          tabIndex={-1}
        />
      </div>
    </div>
  );
}
