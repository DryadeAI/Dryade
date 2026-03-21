// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { usePWAUpdate } from '@/hooks/usePWA';
import { Button } from '@/components/ui/button';
import { RefreshCw, X } from 'lucide-react';

export default function PWAUpdatePrompt() {
  const { updateAvailable, applyUpdate, dismissUpdate } = usePWAUpdate();

  if (!updateAvailable) return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-50 animate-slide-up">
      <div className="bg-[hsl(var(--info)/0.15)] border-b border-[hsl(var(--info)/0.3)] px-4 py-2.5 flex items-center justify-center gap-3">
        <p className="text-sm text-foreground">
          A new version is available
        </p>

        <Button
          size="sm"
          variant="outline"
          onClick={applyUpdate}
          className="gap-1.5 h-7 text-xs border-[hsl(var(--info)/0.4)] hover:bg-[hsl(var(--info)/0.1)]"
        >
          <RefreshCw size={12} aria-hidden="true" />
          Update
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 text-muted-foreground hover:text-foreground"
          onClick={dismissUpdate}
          aria-label="Dismiss update notification"
        >
          <X size={12} aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}
