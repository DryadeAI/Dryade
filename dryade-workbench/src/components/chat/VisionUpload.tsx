// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * VisionUpload - Image upload button and preview for vision input.
 * Supports click-to-browse and drag-and-drop.
 */
import React, { useRef, useCallback, useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { toast } from "sonner";
import { ImagePlus, X } from "lucide-react";

export interface ImageAttachment {
  base64: string;
  mimeType: string;
  preview: string;
}

export interface VisionUploadProps {
  onImageSelect: (attachment: ImageAttachment) => void;
  onRemove: () => void;
  attachment: ImageAttachment | null;
  className?: string;
}

const ACCEPTED_TYPES = "image/png,image/jpeg,image/gif,image/webp";
const MAX_SIZE = 10 * 1024 * 1024; // 10MB

function processFile(
  file: File,
  onImageSelect: (attachment: ImageAttachment) => void
) {
  if (!file.type.match(/^image\/(png|jpeg|gif|webp)$/)) {
    toast.error("Unsupported image type", {
      description: "Please upload a PNG, JPEG, GIF, or WebP image.",
    });
    return;
  }

  if (file.size > MAX_SIZE) {
    toast.error("Image too large", {
      description: "Maximum file size is 10MB.",
    });
    return;
  }

  const reader = new FileReader();
  reader.onload = (e) => {
    const dataUrl = e.target?.result as string;
    if (!dataUrl) return;

    // Extract base64 from data URL
    const base64 = dataUrl.split(",")[1];
    onImageSelect({
      base64,
      mimeType: file.type,
      preview: dataUrl,
    });
  };
  reader.readAsDataURL(file);
}

export function VisionUpload({
  onImageSelect,
  onRemove,
  attachment,
  className,
}: VisionUploadProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const handleClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        processFile(file, onImageSelect);
      }
      // Reset input so same file can be re-selected
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    [onImageSelect]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragOver(false);

      const file = e.dataTransfer.files?.[0];
      if (file) {
        processFile(file, onImageSelect);
      }
    },
    [onImageSelect]
  );

  return (
    <div className={cn("flex items-center gap-1", className)}>
      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_TYPES}
        onChange={handleFileChange}
        className="hidden"
        aria-label="Upload image for vision analysis"
      />

      {attachment ? (
        <div className="relative group">
          <img
            src={attachment.preview}
            alt="Attached image preview"
            className="h-8 w-8 rounded object-cover border"
          />
          <button
            onClick={onRemove}
            className="absolute -top-1 -right-1 h-4 w-4 rounded-full bg-destructive text-destructive-foreground flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
            aria-label="Remove attached image"
          >
            <X className="h-2.5 w-2.5" />
          </button>
        </div>
      ) : (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className={cn(
                "h-8 w-8 transition-colors",
                isDragOver && "bg-primary/10 border-primary"
              )}
              onClick={handleClick}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <ImagePlus className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Attach image for vision analysis</TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}

export default VisionUpload;
