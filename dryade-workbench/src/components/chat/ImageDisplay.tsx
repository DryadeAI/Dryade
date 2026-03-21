// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * ImageDisplay - Renders base64-encoded images inline in chat messages.
 * Supports responsive grid layout, loading skeleton, error fallback,
 * and click-to-zoom via shadcn Dialog.
 */
import React, { useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ImageOff } from "lucide-react";
import { ImageControls } from "./ImageControls";

export interface ImageItem {
  data: string;
  mimeType: string;
  alt_text?: string;
}

export interface ImageDisplayProps {
  images: ImageItem[];
  className?: string;
  /** Original prompt used to generate the image (for controls) */
  prompt?: string;
  /** Callback to regenerate image with a new/edited prompt */
  onRegenerate?: (prompt: string) => void;
}

function SingleImage({
  image,
  onClick,
}: {
  image: ImageItem;
  onClick: () => void;
}) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);

  const src = `data:${image.mimeType};base64,${image.data}`;
  const alt = image.alt_text || "Generated image";

  if (error) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-lg border bg-muted/30 p-6 text-muted-foreground text-sm">
        <ImageOff className="h-5 w-5" />
        <span>Failed to load image</span>
      </div>
    );
  }

  return (
    <div className="relative cursor-pointer" onClick={onClick}>
      {!loaded && (
        <Skeleton className="absolute inset-0 rounded-lg" />
      )}
      <img
        src={src}
        alt={alt}
        loading="lazy"
        onLoad={() => setLoaded(true)}
        onError={() => setError(true)}
        className={cn(
          "rounded-lg border bg-muted/30 object-contain max-h-[400px] w-full transition-opacity",
          loaded ? "opacity-100" : "opacity-0"
        )}
      />
    </div>
  );
}

export function ImageDisplay({
  images,
  className,
  prompt,
  onRegenerate,
}: ImageDisplayProps) {
  const [zoomedIndex, setZoomedIndex] = useState<number | null>(null);

  const handleClose = useCallback(() => {
    setZoomedIndex(null);
  }, []);

  if (!images || images.length === 0) return null;

  const gridCols = images.length === 1 ? "grid-cols-1" : "grid-cols-2";

  return (
    <>
      <div className={cn("grid gap-2", gridCols, className)}>
        {images.map((image, idx) => (
          <SingleImage
            key={`img-${idx}`}
            image={image}
            onClick={() => setZoomedIndex(idx)}
          />
        ))}
      </div>

      {/* Image controls (regenerate, edit prompt, download) */}
      {prompt && onRegenerate && (
        <ImageControls
          prompt={prompt}
          onRegenerate={onRegenerate}
          onDownload={() => {}}
          imageData={images[0]?.data}
          imageMimeType={images[0]?.mimeType}
          className="mt-1"
        />
      )}

      {/* Zoom dialog */}
      <Dialog
        open={zoomedIndex !== null}
        onOpenChange={(open) => {
          if (!open) handleClose();
        }}
      >
        <DialogContent className="max-w-[90vw] max-h-[90vh] p-2">
          {zoomedIndex !== null && images[zoomedIndex] && (
            <img
              src={`data:${images[zoomedIndex].mimeType};base64,${images[zoomedIndex].data}`}
              alt={images[zoomedIndex].alt_text || "Generated image (full resolution)"}
              className="max-w-full max-h-[85vh] object-contain mx-auto rounded-lg"
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

export default ImageDisplay;
