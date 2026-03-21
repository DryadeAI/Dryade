// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import React, { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  MessageSquare,
  Brain,
  Search,
  Plus,
  X,
  Trash2,
  Pencil,
  Check,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import type { Conversation, ChatMode } from "@/types/api";

export interface ConversationListProps {
  conversations: Conversation[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onDelete?: (id: string) => void;
  onRename?: (id: string, newTitle: string) => void;
  isLoading?: boolean;
}

const modeConfig: Record<ChatMode, { icon: typeof MessageSquare; color: string }> = {
  chat: { icon: MessageSquare, color: "text-muted-foreground" },
  planner: { icon: Brain, color: "text-accent-secondary" },
};

const ConversationList = React.memo(function ConversationList({
  conversations,
  selectedId,
  onSelect,
  onNewChat,
  onDelete,
  onRename,
  isLoading = false,
}: ConversationListProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const renameInputRef = useRef<HTMLInputElement>(null);

  // Focus rename input when entering rename mode
  useEffect(() => {
    if (renamingId && renameInputRef.current) {
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [renamingId]);

  const filteredConversations = searchQuery.trim()
    ? conversations.filter((c) =>
        (c.title || "").toLowerCase().includes(searchQuery.toLowerCase())
      )
    : conversations;

  const startRename = (conv: Conversation) => {
    setRenamingId(conv.id);
    setRenameValue(conv.title || "");
  };

  const commitRename = () => {
    if (renamingId && renameValue.trim() && onRename) {
      onRename(renamingId, renameValue.trim());
    }
    setRenamingId(null);
    setRenameValue("");
  };

  const cancelRename = () => {
    setRenamingId(null);
    setRenameValue("");
  };

  if (isLoading) {
    return (
      <div className="h-full flex flex-col p-3 border-r border-border">
        <div className="mb-3">
          <Skeleton className="h-9 w-full rounded-lg" />
        </div>
        <Skeleton className="h-9 w-full mb-3" />
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-14 w-full rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-sidebar border-r border-sidebar-border">
      {/* Header */}
      <div className="p-3 border-b border-sidebar-border">
        <Button
          onClick={onNewChat}
          className="w-full gap-2 bg-gradient-to-r from-primary to-accent hover:opacity-90"
        >
          <Plus size={16} />
          New Chat
        </Button>
      </div>

      {/* Search */}
      <div className="p-3">
        <div className="relative">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search conversations..."
            className="pl-9 pr-8 h-9 bg-sidebar-accent border-sidebar-border"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Conversation List */}
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {filteredConversations.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground text-sm">
              {searchQuery ? "No matches found" : "No conversations yet"}
            </div>
          ) : (
            filteredConversations.map((conv) => {
              const mode = modeConfig[conv.mode];
              const ModeIcon = mode.icon;
              const isSelected = conv.id === selectedId;
              const isHovered = conv.id === hoveredId;
              const isRenaming = conv.id === renamingId;

              return (
                <button
                  key={conv.id}
                  onClick={() => !isRenaming && onSelect(conv.id)}
                  onMouseEnter={() => setHoveredId(conv.id)}
                  onMouseLeave={() => setHoveredId(null)}
                  className={cn(
                    "w-full text-left p-3 rounded-lg transition-colors group relative",
                    isSelected
                      ? "bg-sidebar-accent border border-primary/30"
                      : "hover:bg-sidebar-accent"
                  )}
                  aria-selected={isSelected}
                  role="option"
                >
                  <div className="flex items-start gap-2">
                    <ModeIcon size={16} className={cn("mt-0.5", mode.color)} />
                    <div className="flex-1 min-w-0">
                      {isRenaming ? (
                        <div className="flex items-center gap-1">
                          <Input
                            ref={renameInputRef}
                            value={renameValue}
                            onChange={(e) => setRenameValue(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") commitRename();
                              if (e.key === "Escape") cancelRename();
                              e.stopPropagation();
                            }}
                            onClick={(e) => e.stopPropagation()}
                            className="h-6 text-sm px-1 py-0"
                          />
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              commitRename();
                            }}
                            className="p-0.5 text-green-500 hover:text-green-600 transition-colors"
                            aria-label="Confirm rename"
                          >
                            <Check size={14} />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              cancelRename();
                            }}
                            className="p-0.5 text-muted-foreground hover:text-foreground transition-colors"
                            aria-label="Cancel rename"
                          >
                            <X size={14} />
                          </button>
                        </div>
                      ) : (
                        <p
                          className={cn(
                            "text-sm font-medium truncate",
                            isSelected ? "text-primary" : "text-sidebar-foreground"
                          )}
                        >
                          {conv.title || "Untitled"}
                        </p>
                      )}
                      <p className="text-xs text-muted-foreground">
                        {conv.message_count} msgs ·{" "}
                        {formatDistanceToNow(new Date(conv.updated_at), {
                          addSuffix: true,
                        })}
                      </p>
                    </div>

                    {/* Action buttons on hover */}
                    {!isRenaming && isHovered && (
                      <div className="flex items-center gap-0.5">
                        {onRename && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              startRename(conv);
                            }}
                            className="p-1 text-muted-foreground hover:text-foreground transition-colors"
                            aria-label="Rename conversation"
                          >
                            <Pencil size={14} />
                          </button>
                        )}
                        {onDelete && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onDelete(conv.id);
                            }}
                            className="p-1 text-muted-foreground hover:text-destructive transition-colors"
                            aria-label="Delete conversation"
                          >
                            <Trash2 size={14} />
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </button>
              );
            })
          )}
        </div>
      </ScrollArea>
    </div>
  );
});

export default ConversationList;
