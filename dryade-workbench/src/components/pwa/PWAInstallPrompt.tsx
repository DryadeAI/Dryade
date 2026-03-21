// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { usePWAInstall } from '@/hooks/usePWA';
import { Button } from '@/components/ui/button';
import { Download, X } from 'lucide-react';

export default function PWAInstallPrompt() {
  const { canInstall, promptInstall, dismiss } = usePWAInstall();

  if (!canInstall) return null;

  return (
    <div className="fixed bottom-4 right-4 left-4 md:left-auto md:w-80 z-50 animate-slide-up">
      <div className="bg-card border border-border rounded-xl p-4 shadow-elevated flex items-start gap-3">
        {/* App icon */}
        <img
          src="/icons/icon-192x192.png"
          alt=""
          className="w-10 h-10 rounded-lg shrink-0"
          aria-hidden="true"
        />

        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-foreground">Install Dryade</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Access your workbench offline
          </p>

          <div className="flex items-center gap-2 mt-3">
            <Button
              size="sm"
              onClick={promptInstall}
              className="gap-1.5"
            >
              <Download size={14} aria-hidden="true" />
              Install
            </Button>
          </div>
        </div>

        {/* Dismiss */}
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 shrink-0 text-muted-foreground hover:text-foreground"
          onClick={dismiss}
          aria-label="Dismiss install prompt"
        >
          <X size={14} aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}
