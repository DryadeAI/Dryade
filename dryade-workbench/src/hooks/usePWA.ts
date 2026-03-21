// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useEffect, useCallback } from 'react';

// ── Install Hook ────────────────────────────────────────────────

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

interface PWAInstallState {
  canInstall: boolean;
  isInstalled: boolean;
  promptInstall: () => Promise<void>;
}

const DISMISS_KEY = 'dryade-pwa-install-dismissed';
const DISMISS_DURATION_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

function isDismissed(): boolean {
  try {
    const raw = localStorage.getItem(DISMISS_KEY);
    if (!raw) return false;
    const expiry = parseInt(raw, 10);
    if (Date.now() > expiry) {
      localStorage.removeItem(DISMISS_KEY);
      return false;
    }
    return true;
  } catch {
    return false;
  }
}

export function usePWAInstall(): PWAInstallState & { dismiss: () => void } {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [isInstalled, setIsInstalled] = useState(false);
  const [dismissed, setDismissed] = useState(isDismissed);

  useEffect(() => {
    // Check if already installed as standalone
    if (window.matchMedia('(display-mode: standalone)').matches) {
      setIsInstalled(true);
      return;
    }

    const handleBeforeInstall = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
    };

    const handleInstalled = () => {
      setIsInstalled(true);
      setDeferredPrompt(null);
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstall);
    window.addEventListener('appinstalled', handleInstalled);

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstall);
      window.removeEventListener('appinstalled', handleInstalled);
    };
  }, []);

  const promptInstall = useCallback(async () => {
    if (!deferredPrompt) return;
    await deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === 'accepted') {
      setIsInstalled(true);
    }
    setDeferredPrompt(null);
  }, [deferredPrompt]);

  const dismiss = useCallback(() => {
    try {
      localStorage.setItem(DISMISS_KEY, String(Date.now() + DISMISS_DURATION_MS));
    } catch { /* ignore storage errors */ }
    setDismissed(true);
  }, []);

  return {
    canInstall: !!deferredPrompt && !isInstalled && !dismissed,
    isInstalled,
    promptInstall,
    dismiss,
  };
}

// ── Update Hook ─────────────────────────────────────────────────

interface PWAUpdateState {
  updateAvailable: boolean;
  applyUpdate: () => void;
  dismissUpdate: () => void;
}

const UPDATE_DISMISS_KEY = 'dryade-pwa-update-dismissed';

export function usePWAUpdate(): PWAUpdateState {
  const [updateAvailable, setUpdateAvailable] = useState(false);
  const [updateFn, setUpdateFn] = useState<((reloadPage?: boolean) => void) | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    // Check session dismissal
    try {
      if (sessionStorage.getItem(UPDATE_DISMISS_KEY) === '1') {
        setDismissed(true);
      }
    } catch { /* ignore */ }

    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.updateSW) {
        setUpdateFn(() => detail.updateSW);
        setUpdateAvailable(true);
      }
    };

    window.addEventListener('pwa-update-available', handler);
    return () => window.removeEventListener('pwa-update-available', handler);
  }, []);

  const applyUpdate = useCallback(() => {
    if (updateFn) {
      updateFn(true);
    }
  }, [updateFn]);

  const dismissUpdate = useCallback(() => {
    try {
      sessionStorage.setItem(UPDATE_DISMISS_KEY, '1');
    } catch { /* ignore */ }
    setDismissed(true);
  }, []);

  return {
    updateAvailable: updateAvailable && !dismissed,
    applyUpdate,
    dismissUpdate,
  };
}
