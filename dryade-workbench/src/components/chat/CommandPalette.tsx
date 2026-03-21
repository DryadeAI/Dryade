// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// CommandPalette - Ctrl+K command palette dialog
// Extracted from ChatPage to encapsulate the slash-command discovery UI

import React from "react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import type { Command } from "@/hooks/useCommands";
import { Bot, Search, Terminal, Zap } from "lucide-react";

// ============== Icon Mapping ==============

/** Map command names to appropriate icons */
function getCommandIcon(name: string) {
  switch (name.toLowerCase()) {
    case "agent":
      return Bot;
    case "flow":
      return Zap;
    case "rag":
    case "analyze":
      return Search;
    default:
      return Terminal;
  }
}

// ============== Command Palette ==============

interface CommandPaletteProps {
  /** Whether the command palette is open */
  open: boolean;
  /** Callback to change open state */
  onOpenChange: (open: boolean) => void;
  /** Available commands from useCommands hook */
  commands: Command[];
  /** Whether commands are still loading */
  isLoading?: boolean;
  /** Callback when a command is selected for execution */
  onSelectCommand: (command: Command) => void;
}

/**
 * CommandPalette - Global command palette dialog (Ctrl+K / Cmd+K).
 *
 * Displays available backend commands with icons, descriptions, and
 * search/filter capabilities via shadcn CommandDialog.
 *
 * The keyboard shortcut to open this dialog is handled by the parent
 * component (ChatPage registers Ctrl+K listener).
 */
export const CommandPalette = React.memo(function CommandPalette({
  open,
  onOpenChange,
  commands,
  isLoading = false,
  onSelectCommand,
}: CommandPaletteProps) {
  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="Type a command or search..." />
      <CommandList>
        <CommandEmpty>
          {isLoading ? "Loading commands..." : "No commands found."}
        </CommandEmpty>
        <CommandGroup heading="Commands">
          {commands.map((cmd) => {
            const Icon = getCommandIcon(cmd.name);
            return (
              <CommandItem
                key={cmd.name}
                onSelect={() => onSelectCommand(cmd)}
                className="gap-2"
              >
                <Icon size={16} className="text-primary" />
                <div>
                  <p className="font-mono text-sm">/{cmd.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {cmd.description}
                  </p>
                </div>
              </CommandItem>
            );
          })}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
});

export default CommandPalette;
