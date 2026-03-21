// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * ImageControls - Regenerate, edit prompt, and download controls for generated images.
 */
import React, { useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { RefreshCw, Pencil, Download, X } from "lucide-react";

export interface ImageControlsProps {
  /** Original prompt used for generation */
  prompt: string;
  /** Callback to regenerate with a (possibly edited) prompt */
  onRegenerate: (prompt: string) => void;
  /** Callback to download image */
  onDownload: (imageData: string, mimeType: string) => void;
  /** Base64 data of the image to download */
  imageData?: string;
  /** MIME type of the image */
  imageMimeType?: string;
  className?: string;
}

export function ImageControls({
  prompt,
  onRegenerate,
  onDownload,
  imageData,
  imageMimeType = "image/png",
  className,
}: ImageControlsProps) {
  const [editing, setEditing] = useState(false);
  const [editedPrompt, setEditedPrompt] = useState(prompt);

  const handleRegenerate = useCallback(() => {
    onRegenerate(prompt);
  }, [onRegenerate, prompt]);

  const handleEditSubmit = useCallback(() => {
    if (editedPrompt.trim()) {
      onRegenerate(editedPrompt.trim());
      setEditing(false);
    }
  }, [editedPrompt, onRegenerate]);

  const handleDownload = useCallback(() => {
    if (!imageData) return;

    // Convert base64 to blob and trigger download
    const byteChars = atob(imageData);
    const byteArray = new Uint8Array(byteChars.length);
    for (let i = 0; i < byteChars.length; i++) {
      byteArray[i] = byteChars.charCodeAt(i);
    }
    const blob = new Blob([byteArray], { type: imageMimeType });
    const url = URL.createObjectURL(blob);
    const ext = imageMimeType.split("/")[1] || "png";
    const timestamp = Date.now();

    const link = document.createElement("a");
    link.href = url;
    link.download = `dryade-image-${timestamp}.${ext}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [imageData, imageMimeType]);

  if (editing) {
    return (
      <div className={cn("flex items-center gap-2", className)}>
        <Input
          value={editedPrompt}
          onChange={(e) => setEditedPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleEditSubmit();
            if (e.key === "Escape") setEditing(false);
          }}
          className="text-xs h-7 flex-1"
          placeholder="Edit prompt..."
          autoFocus
        />
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={handleEditSubmit}
        >
          Regenerate
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          className="h-7 w-7"
          onClick={() => setEditing(false)}
        >
          <X className="h-3 w-3" />
        </Button>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex items-center gap-1 text-muted-foreground",
        className
      )}
    >
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            className="h-7 w-7"
            onClick={handleRegenerate}
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Regenerate image</TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            className="h-7 w-7"
            onClick={() => {
              setEditedPrompt(prompt);
              setEditing(true);
            }}
          >
            <Pencil className="h-3.5 w-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Edit prompt and regenerate</TooltipContent>
      </Tooltip>

      {imageData && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              className="h-7 w-7"
              onClick={handleDownload}
            >
              <Download className="h-3.5 w-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Download image</TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}

export default ImageControls;
