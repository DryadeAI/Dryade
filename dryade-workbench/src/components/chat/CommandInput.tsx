// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// CommandInput - Chat input with "/" command autocomplete
// Integrates with useCommands hook for backend command discovery

import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { toast } from "sonner";
import type { Command } from "@/hooks/useCommands";
import {
  Send,
  Square,
  Terminal,
  Zap,
  Bot,
  Search as SearchIcon,
} from "lucide-react";
import { VisionUpload } from "./VisionUpload";
import type { ImageAttachment } from "./VisionUpload";

export interface CommandInputProps {
  /** Available commands from useCommands hook */
  commands: Command[];
  /** Callback when command is executed */
  onCommandExecute: (name: string, args: Record<string, unknown>) => void;
  /** Optional: callback for regular message send (non-command) */
  onMessageSend?: (content: string, imageAttachments?: Array<{ base64: string; mime_type: string }>) => void;
  /** Loading state for command execution */
  isExecuting?: boolean;
  /** Loading state for message streaming (shows stop button) */
  isLoading?: boolean;
  /** Callback to stop generation */
  onStop?: () => void;
  /** Disabled state */
  disabled?: boolean;
  /** Placeholder text */
  placeholder?: string;
  /** Get similar command suggestions for typos */
  getSuggestions?: (partial: string) => Command[];
  /** Callback when input gains focus */
  onFocus?: () => void;
  /** Callback when input loses focus */
  onBlur?: () => void;
}

/** Icon mapping for known command types */
const getCommandIcon = (name: string) => {
  switch (name.toLowerCase()) {
    case "agent":
      return Bot;
    case "flow":
      return Zap;
    case "rag":
    case "analyze":
      return SearchIcon;
    default:
      return Terminal;
  }
};

/** Highlight matching characters in command name */
const HighlightedText = ({
  text,
  highlight,
}: {
  text: string;
  highlight: string;
}) => {
  if (!highlight) return <span>{text}</span>;

  const normalizedHighlight = highlight.toLowerCase().replace(/^\//, "");
  const normalizedText = text.toLowerCase();
  const index = normalizedText.indexOf(normalizedHighlight);

  if (index === -1) return <span>{text}</span>;

  return (
    <span>
      {text.slice(0, index)}
      <span className="bg-primary/20 text-primary font-medium">
        {text.slice(index, index + normalizedHighlight.length)}
      </span>
      {text.slice(index + normalizedHighlight.length)}
    </span>
  );
};

/**
 * CommandInput - Input component with "/" command autocomplete.
 *
 * Features:
 * - Shows dropdown when "/" typed at start of input
 * - Arrow key navigation (up/down)
 * - Enter to select command
 * - Escape to dismiss dropdown
 * - Highlights matching characters
 * - Shows "Did you mean..." for invalid commands
 *
 * @example
 * const { commands, execute, getSuggestions } = useCommands();
 *
 * <CommandInput
 *   commands={commands}
 *   onCommandExecute={(name, args) => execute(name, args)}
 *   getSuggestions={getSuggestions}
 * />
 */
export function CommandInput({
  commands,
  onCommandExecute,
  onMessageSend,
  isExecuting = false,
  isLoading = false,
  onStop,
  disabled = false,
  placeholder,
  getSuggestions,
  onFocus,
  onBlur,
}: CommandInputProps) {
  const { t } = useTranslation('chat');
  const [input, setInput] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [imageAttachment, setImageAttachment] = useState<ImageAttachment | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  // Determine if input is a command (starts with "/")
  const isCommand = input.startsWith("/");
  const commandQuery = isCommand ? input.slice(1) : "";

  // Filter commands based on input
  const filteredCommands = useMemo(() => {
    if (!isCommand || !commandQuery) return commands;

    // Use getSuggestions if available (includes fuzzy matching)
    if (getSuggestions) {
      return getSuggestions(commandQuery);
    }

    // Fallback: simple prefix/contains filtering
    const query = commandQuery.toLowerCase();
    return commands.filter(
      (cmd) =>
        cmd.name.toLowerCase().startsWith(query) ||
        cmd.name.toLowerCase().includes(query)
    );
  }, [commands, commandQuery, isCommand, getSuggestions]);

  // Show dropdown when typing "/" and there are commands
  useEffect(() => {
    if (isCommand && commands.length > 0) {
      setIsOpen(true);
      setSelectedIndex(0);
    } else {
      setIsOpen(false);
    }
  }, [isCommand, commands.length]);

  // Scroll selected item into view
  useEffect(() => {
    if (!listRef.current || !isOpen) return;
    const items = listRef.current.querySelectorAll("[data-command-item]");
    const selectedItem = items[selectedIndex] as HTMLElement;
    if (selectedItem) {
      selectedItem.scrollIntoView({ block: "nearest" });
    }
  }, [selectedIndex, isOpen]);

  /**
   * Handle command selection
   */
  const selectCommand = useCallback(
    (command: Command) => {
      // Execute immediately with empty args
      // Future: could transition to args input mode
      onCommandExecute(command.name, {});
      setInput("");
      setIsOpen(false);
      inputRef.current?.focus();
    },
    [onCommandExecute]
  );

  /**
   * Handle form submission
   */
  const handleSubmit = useCallback(() => {
    if (!input.trim() || isExecuting || disabled) return;

    if (isCommand) {
      const commandName = commandQuery.split(/\s+/)[0];

      // Check if command exists
      const exactMatch = commands.find(
        (cmd) => cmd.name.toLowerCase() === commandName.toLowerCase()
      );

      if (exactMatch) {
        // Execute the matched command
        selectCommand(exactMatch);
        return;
      }

      // No exact match - show suggestions
      const suggestions = getSuggestions
        ? getSuggestions(commandName)
        : filteredCommands;

      if (suggestions.length > 0) {
        toast.error(t('input.commandNotFound', { name: commandName }), {
          description: t('input.didYouMean', {
            suggestions: suggestions
              .slice(0, 3)
              .map((s) => `/${s.name}`)
              .join(", "),
          }),
        });
      } else {
        toast.error(t('input.commandNotFound', { name: commandName }), {
          description: t('input.typeSlashForCommands'),
        });
      }
      return;
    }

    // Regular message (non-command)
    if (onMessageSend) {
      const attachments = imageAttachment
        ? [{ base64: imageAttachment.base64, mime_type: imageAttachment.mimeType }]
        : undefined;
      onMessageSend(input.trim(), attachments);
      setInput("");
      setImageAttachment(null);
    }
  }, [
    input,
    isExecuting,
    disabled,
    isCommand,
    commandQuery,
    commands,
    selectCommand,
    getSuggestions,
    filteredCommands,
    onMessageSend,
  ]);

  /**
   * Handle keyboard navigation
   */
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (!isOpen) {
        if (e.key === "Enter") {
          e.preventDefault();
          handleSubmit();
        }
        return;
      }

      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setSelectedIndex((prev) =>
            prev < filteredCommands.length - 1 ? prev + 1 : 0
          );
          break;
        case "ArrowUp":
          e.preventDefault();
          setSelectedIndex((prev) =>
            prev > 0 ? prev - 1 : filteredCommands.length - 1
          );
          break;
        case "Enter":
          e.preventDefault();
          if (filteredCommands[selectedIndex]) {
            selectCommand(filteredCommands[selectedIndex]);
          } else {
            handleSubmit();
          }
          break;
        case "Escape":
          e.preventDefault();
          setIsOpen(false);
          break;
        case "Tab":
          // Tab completes the selected command
          if (filteredCommands[selectedIndex]) {
            e.preventDefault();
            setInput(`/${filteredCommands[selectedIndex].name} `);
          }
          break;
      }
    },
    [isOpen, filteredCommands, selectedIndex, selectCommand, handleSubmit]
  );

  return (
    <div className="relative w-full">
      <Popover open={isOpen} onOpenChange={(open) => {
        // Only allow closing via onOpenChange, not opening
        // Opening is controlled by "/" input detection in useEffect
        if (!open) setIsOpen(false);
      }}>
        <PopoverTrigger asChild>
          <div className="relative">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSubmit();
              }}
              className="flex gap-2"
            >
              <div className="relative flex-1">
                <Input
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  onFocus={() => {
                    // Don't auto-open on focus - only open when "/" is typed
                    onFocus?.();
                  }}
                  onBlur={() => {
                    onBlur?.();
                  }}
                  placeholder={placeholder || t('input.defaultPlaceholder')}
                  disabled={disabled || isExecuting}
                  className={cn(
                    "pr-10",
                    isCommand && "font-mono text-primary"
                  )}
                  aria-label="Message or command input"
                  data-testid="chat-message-input"
                  aria-expanded={isOpen}
                  aria-haspopup="listbox"
                  aria-controls="command-list"
                  role="combobox"
                />
                {isCommand && (
                  <div className="absolute right-3 top-1/2 -translate-y-1/2">
                    <Terminal
                      size={14}
                      className="text-primary motion-safe:animate-pulse"
                    />
                  </div>
                )}
              </div>
              <VisionUpload
                attachment={imageAttachment}
                onImageSelect={setImageAttachment}
                onRemove={() => setImageAttachment(null)}
              />
              {isLoading ? (
                <Button
                  type="button"
                  size="icon"
                  variant="destructive"
                  onClick={onStop}
                  className="transition-all duration-150"
                  aria-label="Stop generation"
                >
                  <Square size={16} />
                </Button>
              ) : (
                <Button
                  type="submit"
                  size="icon"
                  disabled={!input.trim() || isExecuting || disabled}
                  className={cn(
                    "transition-all duration-150",
                    input.trim() ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                  )}
                  aria-label="Send message"
                  data-testid="chat-send-button"
                >
                  <Send size={16} />
                </Button>
              )}
            </form>
          </div>
        </PopoverTrigger>

        <PopoverContent
          className="w-[var(--radix-popover-trigger-width)] p-0"
          align="start"
          sideOffset={4}
          onOpenAutoFocus={(e) => e.preventDefault()}
        >
          <div
            ref={listRef}
            id="command-list"
            role="listbox"
            className="max-h-60 overflow-y-auto p-1"
          >
            {filteredCommands.length === 0 ? (
              <div className="py-6 text-center text-sm text-muted-foreground">
                {t('input.noCommandsFound')}
              </div>
            ) : (
              filteredCommands.map((command, index) => {
                const Icon = getCommandIcon(command.name);
                return (
                  <button
                    key={command.name}
                    data-command-item
                    role="option"
                    aria-selected={index === selectedIndex}
                    onClick={() => selectCommand(command)}
                    className={cn(
                      "w-full flex items-start gap-3 px-3 py-2 rounded-md cursor-pointer transition-colors text-left",
                      index === selectedIndex
                        ? "bg-accent text-accent-foreground"
                        : "hover:bg-muted"
                    )}
                  >
                    <div className="p-1.5 rounded-md bg-primary/10 shrink-0">
                      <Icon size={14} className="text-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-mono text-sm">
                        /
                        <HighlightedText
                          text={command.name}
                          highlight={commandQuery}
                        />
                      </div>
                      <div className="text-xs text-muted-foreground truncate">
                        {command.description}
                      </div>
                    </div>
                  </button>
                );
              })
            )}
          </div>

          {/* Keyboard hints */}
          <div className="border-t border-border px-3 py-1.5 flex items-center justify-between text-[10px] text-muted-foreground">
            <span>
              <kbd className="px-1 rounded bg-muted font-mono">Tab</kbd> {t('input.tabComplete')}
            </span>
            <span>
              <kbd className="px-1 rounded bg-muted font-mono">Enter</kbd> {t('input.enterSelect')}
            </span>
            <span>
              <kbd className="px-1 rounded bg-muted font-mono">Esc</kbd> {t('input.escCancel')}
            </span>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}

export default CommandInput;
