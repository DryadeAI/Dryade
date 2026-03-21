// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * SlotErrorBoundary - Error boundary wrapper for slot components
 *
 * Isolates plugin errors to their slot, preventing a single plugin
 * from crashing the entire page.
 */

import { ErrorBoundary } from 'react-error-boundary';
import type { ReactNode } from 'react';

interface SlotErrorProps {
  pluginName: string;
  error: Error;
}

/**
 * Fallback component shown when a slot component crashes
 */
function SlotErrorFallback({ pluginName, error }: SlotErrorProps) {
  return (
    <div className="p-2 text-xs text-destructive bg-destructive/10 rounded border border-destructive/20">
      <span className="font-medium">{pluginName}</span>: Plugin error
      {process.env.NODE_ENV === 'development' && (
        <pre className="mt-1 text-[10px] whitespace-pre-wrap opacity-75">
          {error.message}
        </pre>
      )}
    </div>
  );
}

interface SlotErrorBoundaryProps {
  pluginName: string;
  children: ReactNode;
}

/**
 * Error boundary that wraps individual slot components.
 * Catches errors and displays a contained error message without crashing the page.
 */
export function SlotErrorBoundary({
  pluginName,
  children,
}: SlotErrorBoundaryProps) {
  return (
    <ErrorBoundary
      fallbackRender={({ error }) => (
        <SlotErrorFallback pluginName={pluginName} error={error instanceof Error ? error : new Error(String(error))} />
      )}
      onError={(error) => {
        console.error(`Slot error in plugin ${pluginName}:`, error);
      }}
    >
      {children}
    </ErrorBoundary>
  );
}
