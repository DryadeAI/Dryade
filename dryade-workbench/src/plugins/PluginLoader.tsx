// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useEffect, useCallback, useRef } from 'react';
import { PluginRegistry } from './PluginRegistry';
import { PluginSandbox } from './PluginSandbox';
import { verifyManifestSignature, computeSHA256Hex } from '@/ee/crypto/verifySignature.ee';
import { pluginsApi } from '@/services/api';
import type { PluginManifest } from './types/pluginManifest';
import { hasUI } from './types/pluginManifest';
import { usePreferences } from '@/hooks/usePreferences';
import { AlertCircle, Loader2, ShieldAlert, ShieldCheck } from 'lucide-react';

export type LoaderState =
  | 'idle'
  | 'fetching-manifest'
  | 'verifying-signature'
  | 'fetching-bundle'
  | 'fetching-styles'
  | 'verifying-bundle'
  | 'loading'
  | 'loaded'
  | 'error';

interface PluginLoaderProps {
  pluginName: string;
  className?: string;
  onLoad?: () => void;
  onError?: (error: string) => void;
}

/**
 * PluginLoader - Secure verification-before-load flow
 *
 * Security flow:
 * 1. Fetch manifest from backend
 * 2. Verify manifest Ed25519 signature (MUST complete before bundle fetch)
 * 3. Register verified manifest in PluginRegistry
 * 4. Fetch UI bundle as text
 * 5. Verify bundle SHA-256 hash matches manifest.ui_bundle_hash
 * 6. Only then inject into sandboxed iframe
 *
 * Any verification failure = no code execution
 */
export function PluginLoader({
  pluginName,
  className = '',
  onLoad,
  onError,
}: PluginLoaderProps) {
  const { resolvedTheme } = usePreferences();
  const [state, setState] = useState<LoaderState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [manifest, setManifest] = useState<PluginManifest | null>(null);
  const [bundleCode, setBundleCode] = useState<string | null>(null);
  const [styles, setStyles] = useState<string | null>(null);

  // Use refs for callbacks to avoid re-triggering effect
  const onLoadRef = useRef(onLoad);
  const onErrorRef = useRef(onError);
  const loadingRef = useRef(false);

  // Keep refs updated
  onLoadRef.current = onLoad;
  onErrorRef.current = onError;

  const loadPlugin = useCallback(async () => {
    // Prevent duplicate loads
    if (loadingRef.current) return;
    loadingRef.current = true;
    try {
      // Step 1: Fetch manifest
      setState('fetching-manifest');
      const fetchedManifest = await pluginsApi.getPluginUIManifest(pluginName);

      if (!fetchedManifest) {
        throw new Error(`Plugin ${pluginName} has no UI manifest`);
      }

      if (!hasUI(fetchedManifest)) {
        throw new Error(`Plugin ${pluginName} manifest missing UI fields`);
      }

      // Step 2: Verify manifest signature
      setState('verifying-signature');
      const signatureValid = await verifyManifestSignature(fetchedManifest);

      if (!signatureValid) {
        // SECURITY: Invalid signature - do NOT proceed
        const error = `SECURITY: Invalid signature for plugin ${pluginName}`;
        console.error(error);
        // Could report to telemetry endpoint here
        throw new Error(error);
      }

      // Step 3: Register verified manifest
      PluginRegistry.register(fetchedManifest);
      setManifest(fetchedManifest);

      // Step 4: Fetch bundle
      setState('fetching-bundle');
      const bundle = await pluginsApi.getPluginUIBundle(pluginName);

      // Step 5: Verify bundle hash
      setState('verifying-bundle');
      const actualHash = await computeSHA256Hex(bundle);

      // Compare with manifest hash (normalize format)
      const expectedHash = fetchedManifest.ui_bundle_hash.replace(/^sha256-/, '');

      if (actualHash !== expectedHash) {
        // SECURITY: Bundle tampered - do NOT execute
        const error = `SECURITY: Bundle integrity check failed for ${pluginName}`;
        console.error(error, { expected: expectedHash, actual: actualHash });
        throw new Error(error);
      }

      // Step 6: Fetch styles (optional - plugins may not have separate CSS)
      setState('fetching-styles');
      const pluginStyles = await pluginsApi.getPluginUIStyles(pluginName);
      console.log(`[PluginLoader] Styles fetched for ${pluginName}:`, pluginStyles ? `${pluginStyles.length} chars` : 'null');

      // Step 7: All verification passed - safe to load
      setState('loading');
      setBundleCode(bundle);
      setStyles(pluginStyles);
      setState('loaded');
      onLoadRef.current?.();

    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      setState('error');
      PluginRegistry.markError(pluginName, errorMessage);
      onErrorRef.current?.(errorMessage);
    } finally {
      loadingRef.current = false;
    }
  }, [pluginName]);

  useEffect(() => {
    loadPlugin();
  }, [loadPlugin]);

  // Render loading states
  if (state === 'error') {
    const isSecurityError = error?.includes('SECURITY');
    return (
      <div className={`flex flex-col items-center justify-center p-8 ${className}`} role="alert">
        {isSecurityError ? (
          <ShieldAlert className="w-12 h-12 text-destructive mb-4" aria-hidden="true" />
        ) : (
          <AlertCircle className="w-12 h-12 text-destructive mb-4" aria-hidden="true" />
        )}
        <h3 className="text-lg font-semibold text-destructive mb-2">
          {isSecurityError ? 'Security Verification Failed' : 'Plugin Load Error'}
        </h3>
        <p className="text-sm text-muted-foreground text-center max-w-md">
          {error}
        </p>
      </div>
    );
  }

  if (state !== 'loaded' || !manifest || !bundleCode) {
    const stateProgress: Record<string, number> = {
      'idle': 0,
      'fetching-manifest': 15,
      'verifying-signature': 30,
      'fetching-bundle': 50,
      'verifying-bundle': 65,
      'fetching-styles': 80,
      'loading': 95,
    };

    const stateLabels: Record<string, string> = {
      'idle': 'Initializing...',
      'fetching-manifest': 'Fetching plugin manifest...',
      'verifying-signature': 'Verifying signature...',
      'fetching-bundle': 'Downloading plugin UI...',
      'verifying-bundle': 'Verifying bundle integrity...',
      'fetching-styles': 'Loading styles...',
      'loading': 'Initializing plugin...',
    };

    const progress = stateProgress[state] ?? 0;

    return (
      <div className={`flex flex-col items-center justify-center p-8 gap-4 ${className}`} role="status">
        <Loader2 className="w-8 h-8 motion-safe:animate-spin text-primary" aria-hidden="true" />
        <div className="w-64 space-y-2">
          <div
            className="h-2 rounded-full bg-muted overflow-hidden"
            role="progressbar"
            aria-valuenow={progress}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Loading plugin"
          >
            <div
              className="h-full rounded-full bg-primary motion-safe:transition-all motion-safe:duration-500 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-sm text-muted-foreground text-center flex items-center justify-center gap-2">
            {(state === 'verifying-signature' || state === 'verifying-bundle') && (
              <ShieldCheck className="w-4 h-4" aria-hidden="true" />
            )}
            {stateLabels[state] || 'Loading...'}
          </p>
        </div>
      </div>
    );
  }

  // All verification passed - render sandbox
  return (
    <PluginSandbox
      pluginName={pluginName}
      bundleCode={bundleCode}
      styles={styles ?? undefined}
      permissions={manifest.ui?.permissions || []}
      theme={resolvedTheme}
      className={className}
      onReady={() => console.debug(`Plugin ${pluginName} ready`)}
      onError={(err) => {
        setError(err);
        setState('error');
      }}
    />
  );
}
