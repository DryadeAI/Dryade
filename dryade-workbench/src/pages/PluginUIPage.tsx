// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useParams, Navigate } from 'react-router-dom';
import { PluginLoader } from '@/plugins/PluginLoader';
import { useSinglePluginUI } from '@/hooks/usePluginUI';
import { useAudioCapture } from '@/hooks/useAudioCapture';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { AlertCircle, Mic, Monitor, Puzzle } from 'lucide-react';

// Free-core plugins render as native workbench pages (Phase 191)
const FREE_CORE_REDIRECTS: Record<string, string> = {
  cost_tracker: '/workspace/cost-tracker',
  clarify: '/workspace/clarify-preferences',
};

/**
 * PluginUIPage - Container for plugin UI rendering
 *
 * Uses URL params to determine which plugin to load.
 * Route: /workspace/plugins/:pluginName
 *
 * Special handling for audio plugin:
 * - Enables host-side audio capture via useAudioCapture hook
 * - Shows recording indicator when capturing
 * - Plugin requests capture via PluginBridge messaging
 */
export function PluginUIPage() {
  const { pluginName } = useParams<{ pluginName: string }>();
  const { state, error } = useSinglePluginUI(pluginName || '');

  // Special handling for audio plugin - enable host-side capture
  const isAudioPlugin = pluginName === 'audio';
  const {
    isCapturing,
    systemAudioActive,
    error: audioError,
  } = useAudioCapture({
    pluginName: pluginName || '',
    sampleRate: 16000,
    onError: (err) => console.error('Audio capture error:', err),
  });

  // Redirect free-core plugins to their native pages
  if (pluginName && FREE_CORE_REDIRECTS[pluginName]) {
    return <Navigate to={FREE_CORE_REDIRECTS[pluginName]} replace />;
  }

  if (!pluginName) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8">
        <AlertCircle className="w-12 h-12 text-destructive mb-4" aria-hidden="true" />
        <h2 className="text-xl font-semibold mb-2">Plugin Not Found</h2>
        <p className="text-muted-foreground">No plugin name specified in URL.</p>
      </div>
    );
  }

  if (state === 'error' && error) {
    return (
      <div className="flex items-center justify-center h-full">
        <Alert variant="destructive" className="max-w-md">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="h-full w-full relative">
      {/* Audio capture indicator for audio plugin */}
      {isAudioPlugin && isCapturing && (
        <div className="absolute top-2 right-2 z-10 flex items-center gap-2 bg-destructive text-destructive-foreground px-3 py-1.5 rounded-full text-sm shadow-lg">
          <span className="w-2 h-2 bg-destructive-foreground rounded-full motion-safe:animate-pulse" />
          Recording
          <div className="flex items-center gap-1 ml-1 pl-1.5 border-l border-white/30">
            <Mic className="w-3.5 h-3.5" aria-hidden="true" />
            {systemAudioActive && (
              <Monitor className="w-3.5 h-3.5" aria-hidden="true" />
            )}
          </div>
        </div>
      )}

      {/* Plugin loader with verification flow */}
      <PluginLoader
        pluginName={pluginName}
        className="h-full w-full"
        onLoad={() => console.debug(`Plugin ${pluginName} loaded`)}
        onError={(err) => console.error(`Plugin ${pluginName} error:`, err)}
      />

      {/* Audio error display */}
      {isAudioPlugin && audioError && (
        <div className="absolute bottom-2 right-2 z-10">
          <Alert variant="destructive" className="max-w-sm">
            <AlertDescription>{audioError}</AlertDescription>
          </Alert>
        </div>
      )}
    </div>
  );
}

/**
 * PluginUIHeader - Optional header with plugin info
 *
 * Accepts state and error as props to avoid a duplicate fetch.
 * The parent (PluginUIPage) already calls useSinglePluginUI,
 * so pass its results here instead of fetching again.
 */
export function PluginUIHeader({ pluginName, state, error }: { pluginName: string; state: string; error?: string | null }) {
  return (
    <div className="flex items-center gap-3 p-4 border-b">
      <Puzzle className="w-5 h-5 text-primary" aria-hidden="true" />
      <div>
        <h1 className="text-lg font-semibold">{pluginName}</h1>
        <p className="text-xs text-muted-foreground">
          {state === 'loaded' && 'Plugin active'}
          {state === 'loading' && 'Loading...'}
          {state === 'error' && `Error: ${error}`}
        </p>
      </div>
    </div>
  );
}

export default PluginUIPage;
