// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useEffect } from "react";

/**
 * Delays rendering of loading states (skeletons, spinners) to avoid
 * flash-of-loading on fast responses. Returns true only after the
 * specified delay, preventing jarring sub-300ms skeleton flashes.
 */
export function useDelayedShow(delayMs = 300): boolean {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setShow(true), delayMs);
    return () => clearTimeout(timer);
  }, [delayMs]);
  return show;
}
