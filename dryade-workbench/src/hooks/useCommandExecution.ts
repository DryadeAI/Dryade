// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// useCommandExecution - Command execution state and handlers
// Extracted from ChatPage to encapsulate slash-command execution logic

import { useState, useCallback, useEffect } from "react";
import { toast } from "sonner";
import type { Command } from "@/hooks/useCommands";
import type { Message } from "@/components/chat/MessageItem";

interface UseCommandExecutionParams {
  /** The command execution function from useCommands */
  executeCommand: (
    name: string,
    args: Record<string, unknown>
  ) => Promise<{ status: string; result?: unknown; error?: string }>;
  /** Setter for messages state */
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  /** Setter for text input (cleared on command execution) */
  setInput: (value: string) => void;
  /** Setter for scroll state (reset on command execution) */
  setUserScrolled: (value: boolean) => void;
}

interface CommandExecutionState {
  /** Whether a command is currently executing */
  isExecutingCommand: boolean;
  /** Whether the Ctrl+K command palette is open */
  commandOpen: boolean;
  /** Set the command palette open state */
  setCommandOpen: (open: boolean) => void;
  /** Execute a command by name with arguments */
  handleCommandExecute: (
    name: string,
    args: Record<string, unknown>
  ) => Promise<void>;
  /** Handle command selection from the palette (executes + closes) */
  handleCommandSelect: (command: Command) => void;
}

/**
 * Hook for managing command execution state and the Ctrl+K palette.
 *
 * Handles:
 * - Command execution with result/error message generation
 * - Ctrl+K keyboard shortcut to open the command palette
 * - Command palette open/close state
 * - User/assistant message creation for command results
 */
export function useCommandExecution({
  executeCommand,
  setMessages,
  setInput,
  setUserScrolled,
}: UseCommandExecutionParams): CommandExecutionState {
  const [isExecutingCommand, setIsExecutingCommand] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);

  // Register Ctrl+K keyboard shortcut
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setCommandOpen(true);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const handleCommandExecute = useCallback(
    async (name: string, args: Record<string, unknown>) => {
      setIsExecutingCommand(true);
      setInput("");
      setUserScrolled(false);

      const userMessage: Message = {
        id: `cmd-${Date.now()}`,
        role: "user",
        content: `/${name}${Object.keys(args).length > 0 ? ` ${JSON.stringify(args)}` : ""}`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMessage]);

      try {
        const result = await executeCommand(name, args);

        let resultContent: string;
        if (result.status === "error") {
          resultContent = `Command error: ${result.error || "Unknown error"}`;
        } else if (typeof result.result === "string") {
          resultContent = result.result;
        } else {
          resultContent = `Command executed successfully:\n\`\`\`json\n${JSON.stringify(result.result, null, 2)}\n\`\`\``;
        }

        const assistantMessage: Message = {
          id: `cmd-${Date.now()}-response`,
          role: "assistant",
          content: resultContent,
          timestamp: new Date(),
          model: "command",
        };
        setMessages((prev) => [...prev, assistantMessage]);
      } catch (error) {
        const errorMessage =
          error instanceof Error ? error.message : "Command execution failed";

        const suggestions =
          (error as { suggestions?: string[] })?.suggestions || [];

        toast.error("Command failed", {
          description:
            suggestions.length > 0
              ? `${errorMessage}. Did you mean: ${suggestions.map((s) => `/${s}`).join(", ")}?`
              : errorMessage,
        });

        const errorResponse: Message = {
          id: `cmd-${Date.now()}-error`,
          role: "assistant",
          content: `Failed to execute /${name}: ${errorMessage}`,
          timestamp: new Date(),
          model: "command",
        };
        setMessages((prev) => [...prev, errorResponse]);
      } finally {
        setIsExecutingCommand(false);
      }
    },
    [executeCommand, setMessages, setInput, setUserScrolled]
  );

  const handleCommandSelect = useCallback(
    (command: Command) => {
      handleCommandExecute(command.name, {});
      setCommandOpen(false);
    },
    [handleCommandExecute]
  );

  return {
    isExecutingCommand,
    commandOpen,
    setCommandOpen,
    handleCommandExecute,
    handleCommandSelect,
  };
}
