// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useCallback } from "react";
import { Upload, CheckCircle2, Loader2, Package, AlertCircle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { pluginsApi } from "@/services/api";

type UploadStep = 'idle' | 'uploading' | 'validating' | 'installing' | 'complete' | 'error';

interface PackageUploadProps {
  onInstallComplete?: () => void;
  className?: string;
}

const STEPS: Record<UploadStep, { label: string; progress: number }> = {
  idle: { label: 'Drop .dryadepkg file here', progress: 0 },
  uploading: { label: 'Uploading...', progress: 25 },
  validating: { label: 'Validating signatures...', progress: 50 },
  installing: { label: 'Installing plugin...', progress: 75 },
  complete: { label: 'Installation complete!', progress: 100 },
  error: { label: 'Installation failed', progress: 0 },
};

export const PackageUpload = ({ onInstallComplete, className }: PackageUploadProps) => {
  const [step, setStep] = useState<UploadStep>('idle');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = useCallback(async (file: File) => {
    if (!file.name.endsWith('.dryadepkg')) {
      toast.error('Please upload a .dryadepkg file');
      return;
    }

    setError(null);
    setStep('uploading');

    try {
      // Upload with progress tracking
      setStep('uploading');
      const result = await pluginsApi.uploadPackage(file, (progress) => {
        setUploadProgress(progress);
        if (progress === 100) {
          setStep('validating');
        }
      });

      // Simulate steps (backend does all in one call, but show progress)
      setStep('validating');
      await new Promise(r => setTimeout(r, 500));

      setStep('installing');
      await new Promise(r => setTimeout(r, 500));

      setStep('complete');
      toast.success(`Plugin "${result.plugin_name}" installed successfully`);

      // Reset after delay
      setTimeout(() => {
        setStep('idle');
        setUploadProgress(0);
        onInstallComplete?.();
      }, 2000);

    } catch (err: unknown) {
      setStep('error');
      const message = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || (err instanceof Error ? err.message : 'Installation failed');
      setError(message);
      toast.error(message);
    }
  }, [onInstallComplete]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const file = e.dataTransfer.files[0];
    if (file) {
      handleFile(file);
    }
  }, [handleFile]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleFile(file);
    }
  }, [handleFile]);

  const isProcessing = ['uploading', 'validating', 'installing'].includes(step);

  return (
    <Card className={cn("border-dashed", className)}>
      <CardContent className="p-6">
        <div
          className={cn(
            "relative flex flex-col items-center justify-center gap-4 p-6 rounded-lg border-2 border-dashed transition-colors",
            isDragging && "border-primary bg-primary/5",
            step === 'error' && "border-destructive bg-destructive/5",
            step === 'complete' && "border-success bg-success/5",
            !isDragging && step === 'idle' && "border-muted-foreground/25 hover:border-muted-foreground/50"
          )}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
        >
          {step === 'idle' && (
            <>
              <Package className="w-10 h-10 text-muted-foreground" />
              <div className="text-center">
                <p className="text-sm font-medium">{STEPS[step].label}</p>
                <p className="text-xs text-muted-foreground mt-1">or click to browse</p>
              </div>
              <input
                type="file"
                accept=".dryadepkg"
                onChange={handleInputChange}
                className="absolute inset-0 opacity-0 cursor-pointer"
              />
            </>
          )}

          {isProcessing && (
            <>
              <Loader2 className="w-10 h-10 text-primary animate-spin" />
              <div className="text-center w-full max-w-xs">
                <p className="text-sm font-medium">{STEPS[step].label}</p>
                <Progress value={STEPS[step].progress} className="mt-2" />
              </div>
            </>
          )}

          {step === 'complete' && (
            <>
              <CheckCircle2 className="w-10 h-10 text-success" />
              <p className="text-sm font-medium text-success">{STEPS[step].label}</p>
            </>
          )}

          {step === 'error' && (
            <>
              <AlertCircle className="w-10 h-10 text-destructive" />
              <div className="text-center">
                <p className="text-sm font-medium text-destructive">{STEPS[step].label}</p>
                {error && <p className="text-xs text-muted-foreground mt-1">{error}</p>}
              </div>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
};
