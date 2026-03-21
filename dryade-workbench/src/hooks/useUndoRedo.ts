// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useCallback, useRef } from "react";
import { toast } from "sonner";

interface UseUndoRedoOptions<T> {
  maxHistory?: number;
  onUndo?: (state: T) => void;
  onRedo?: (state: T) => void;
}

interface UseUndoRedoReturn<T> {
  pushState: (state: T) => void;
  undo: () => T | null;
  redo: () => T | null;
  canUndo: boolean;
  canRedo: boolean;
  clear: () => void;
}

export function useUndoRedo<T>(
  initialState: T,
  options: UseUndoRedoOptions<T> = {}
): UseUndoRedoReturn<T> {
  const { maxHistory = 50, onUndo, onRedo } = options;

  const [history, setHistory] = useState<T[]>([initialState]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const isUndoRedoAction = useRef(false);

  const pushState = useCallback(
    (state: T) => {
      if (isUndoRedoAction.current) {
        isUndoRedoAction.current = false;
        return;
      }

      setHistory((prev) => {
        // Remove any future states if we're not at the end
        const newHistory = prev.slice(0, currentIndex + 1);
        newHistory.push(state);

        // Limit history size
        if (newHistory.length > maxHistory) {
          return newHistory.slice(-maxHistory);
        }
        return newHistory;
      });
      setCurrentIndex((prev) => Math.min(prev + 1, maxHistory - 1));
    },
    [currentIndex, maxHistory]
  );

  const undo = useCallback(() => {
    if (currentIndex <= 0) return null;

    isUndoRedoAction.current = true;
    const newIndex = currentIndex - 1;
    setCurrentIndex(newIndex);
    const state = history[newIndex];
    onUndo?.(state);
    toast.info("Undo", { duration: 1500 });
    return state;
  }, [currentIndex, history, onUndo]);

  const redo = useCallback(() => {
    if (currentIndex >= history.length - 1) return null;

    isUndoRedoAction.current = true;
    const newIndex = currentIndex + 1;
    setCurrentIndex(newIndex);
    const state = history[newIndex];
    onRedo?.(state);
    toast.info("Redo", { duration: 1500 });
    return state;
  }, [currentIndex, history, onRedo]);

  const clear = useCallback(() => {
    setHistory([history[currentIndex]]);
    setCurrentIndex(0);
  }, [history, currentIndex]);

  return {
    pushState,
    undo,
    redo,
    canUndo: currentIndex > 0,
    canRedo: currentIndex < history.length - 1,
    clear,
  };
}
