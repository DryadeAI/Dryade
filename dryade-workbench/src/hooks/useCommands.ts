// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// useCommands Hook - Command discovery and execution for slash commands
// Integrates with backend /api/commands endpoints from 36-02

import { useState, useEffect, useCallback, useMemo } from "react";
import { fetchWithAuth } from "@/services/apiClient";

/**
 * Command definition from backend
 */
export interface Command {
  name: string;
  description: string;
}

/**
 * Response from GET /api/commands
 */
interface CommandListResponse {
  commands: Command[];
}

/**
 * Response from POST /api/commands/{name}/execute
 */
interface CommandExecuteResponse {
  status: "ok" | "error";
  result?: unknown;
  error?: string;
}

/**
 * Error response with suggestions when command not found
 */
interface CommandNotFoundError {
  error: string;
  suggestions: string[];
}

export interface UseCommandsReturn {
  /** Available commands from backend */
  commands: Command[];
  /** Loading state for initial fetch */
  isLoading: boolean;
  /** Error from command fetch */
  error: Error | null;
  /** Execute a command by name with optional args */
  execute: (name: string, args?: Record<string, unknown>) => Promise<CommandExecuteResponse>;
  /** Get filtered command suggestions based on partial input */
  getSuggestions: (partial: string) => Command[];
  /** Refresh commands from backend */
  refresh: () => Promise<void>;
}

/**
 * Calculate Levenshtein distance between two strings
 * Used for "Did you mean..." suggestions on typos
 */
function levenshteinDistance(a: string, b: string): number {
  const matrix: number[][] = [];

  for (let i = 0; i <= b.length; i++) {
    matrix[i] = [i];
  }
  for (let j = 0; j <= a.length; j++) {
    matrix[0][j] = j;
  }

  for (let i = 1; i <= b.length; i++) {
    for (let j = 1; j <= a.length; j++) {
      if (b.charAt(i - 1) === a.charAt(j - 1)) {
        matrix[i][j] = matrix[i - 1][j - 1];
      } else {
        matrix[i][j] = Math.min(
          matrix[i - 1][j - 1] + 1, // substitution
          matrix[i][j - 1] + 1,     // insertion
          matrix[i - 1][j] + 1      // deletion
        );
      }
    }
  }

  return matrix[b.length][a.length];
}

/**
 * Hook for command discovery and execution.
 *
 * Features:
 * - Fetches commands from backend on mount
 * - Provides execute function for POST /api/commands/{name}/execute
 * - getSuggestions filters commands by prefix (case-insensitive)
 * - Falls back to Levenshtein distance for typo suggestions
 *
 * @example
 * const { commands, execute, getSuggestions } = useCommands();
 *
 * // Get suggestions as user types
 * const suggestions = getSuggestions("ag"); // Returns commands starting with "ag"
 *
 * // Execute a command
 * const result = await execute("agent", { agent: "test.assistant" });
 */
export function useCommands(): UseCommandsReturn {
  const [commands, setCommands] = useState<Command[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  /**
   * Fetch commands from backend
   */
  const fetchCommands = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetchWithAuth<CommandListResponse>("/commands");
      setCommands(response.commands || []);
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      setError(error);
      console.error("Failed to fetch commands:", error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Fetch commands on mount
  useEffect(() => {
    fetchCommands();
  }, [fetchCommands]);

  /**
   * Execute a command by name
   */
  const execute = useCallback(
    async (name: string, args?: Record<string, unknown>): Promise<CommandExecuteResponse> => {
      try {
        const response = await fetchWithAuth<CommandExecuteResponse>(
          `/commands/${encodeURIComponent(name)}/execute`,
          {
            method: "POST",
            body: JSON.stringify({ args: args || {} }),
          }
        );
        return response;
      } catch (err) {
        // Check if it's a 404 with suggestions
        if (err instanceof Error && err.message.includes("not found")) {
          // Try to extract suggestions from error message
          const match = err.message.match(/Did you mean: ([^?]+)/);
          const suggestions = match ? match[1].split(", ").map((s) => s.trim()) : [];
          throw Object.assign(err, { suggestions });
        }
        throw err;
      }
    },
    []
  );

  /**
   * Get command suggestions based on partial input.
   *
   * Priority:
   * 1. Exact prefix match (case-insensitive)
   * 2. Contains match (case-insensitive)
   * 3. Levenshtein distance <= 2 for typo correction
   */
  const getSuggestions = useCallback(
    (partial: string): Command[] => {
      if (!partial) return commands;

      const normalizedPartial = partial.toLowerCase().replace(/^\//, "");
      if (!normalizedPartial) return commands;

      // First: prefix matches
      const prefixMatches = commands.filter((cmd) =>
        cmd.name.toLowerCase().startsWith(normalizedPartial)
      );
      if (prefixMatches.length > 0) return prefixMatches;

      // Second: contains matches
      const containsMatches = commands.filter((cmd) =>
        cmd.name.toLowerCase().includes(normalizedPartial)
      );
      if (containsMatches.length > 0) return containsMatches;

      // Third: fuzzy matches using Levenshtein distance
      const fuzzyMatches = commands
        .map((cmd) => ({
          command: cmd,
          distance: levenshteinDistance(normalizedPartial, cmd.name.toLowerCase()),
        }))
        .filter(({ distance }) => distance <= 2)
        .sort((a, b) => a.distance - b.distance)
        .map(({ command }) => command);

      return fuzzyMatches;
    },
    [commands]
  );

  return useMemo(
    () => ({
      commands,
      isLoading,
      error,
      execute,
      getSuggestions,
      refresh: fetchCommands,
    }),
    [commands, isLoading, error, execute, getSuggestions, fetchCommands]
  );
}

export default useCommands;
