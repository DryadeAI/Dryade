// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useMemo } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Plus,
  Search,
  X,
  MessageSquare,
  Users,
  GitBranch,
  Workflow,
  Trash2,
  PanelRightClose,
  PanelRight,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import type { Conversation, ChatMode } from "@/types/api";

const modeConfig: Record<ChatMode, { icon: typeof MessageSquare; color: string; label: string }> = {
  chat: { icon: MessageSquare, color: "text-muted-foreground", label: "Chat" },
  planner: { icon: GitBranch, color: "text-purple-500", label: "Planner" },
};

interface ConversationsPanelProps {
  conversations: Conversation[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onDelete?: (id: string) => void;
  isLoading?: boolean;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

const groupByDate = (conversations: Conversation[]) => {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);
  const thisWeek = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);

  const groups: { label: string; conversations: Conversation[] }[] = [
    { label: "Today", conversations: [] },
    { label: "Yesterday", conversations: [] },
    { label: "This Week", conversations: [] },
    { label: "Earlier", conversations: [] },
  ];

  (conversations ?? []).forEach((conv) => {
    const updated = new Date(conv.updated_at);
    if (updated >= today) {
      groups[0].conversations.push(conv);
    } else if (updated >= yesterday) {
      groups[1].conversations.push(conv);
    } else if (updated >= thisWeek) {
      groups[2].conversations.push(conv);
    } else {
      groups[3].conversations.push(conv);
    }
  });

  return groups.filter((g) => g.conversations.length > 0);
};

const ConversationsPanel = ({
  conversations,
  selectedId,
  onSelect,
  onNewChat,
  onDelete,
  isLoading = false,
  collapsed = false,
  onToggleCollapse,
}: ConversationsPanelProps) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const filteredConversations = useMemo(() => {
    if (!searchQuery.trim()) return conversations;
    const query = searchQuery.toLowerCase();
    return conversations.filter((c) => c.title.toLowerCase().includes(query));
  }, [conversations, searchQuery]);

  const groupedConversations = useMemo(
    () => groupByDate(filteredConversations),
    [filteredConversations]
  );

  if (collapsed) {
    return (
      <div className="w-12 border-l border-border bg-card/50 flex flex-col items-center py-3 gap-2">
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleCollapse}
          className="h-8 w-8"
        >
          <PanelRight size={16} />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={onNewChat}
          className="h-8 w-8 text-primary"
        >
          <Plus size={16} />
        </Button>
      </div>
    );
  }

  return (
    <div className="w-72 border-l border-border bg-card/50 flex flex-col">
      {/* Header */}
      <div className="p-3 border-b border-border flex items-center justify-between">
        <span className="text-sm font-medium">Conversations</span>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={onNewChat}
            className="h-7 w-7 text-primary"
          >
            <Plus size={14} />
          </Button>
          {onToggleCollapse && (
            <Button
              variant="ghost"
              size="icon"
              onClick={onToggleCollapse}
              className="h-7 w-7"
            >
              <PanelRightClose size={14} />
            </Button>
          )}
        </div>
      </div>

      {/* Search */}
      <div className="p-2 border-b border-border">
        <div className="relative">
          <Search
            size={14}
            className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search..."
            className="pl-8 pr-7 h-8 text-sm"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      {/* List */}
      <ScrollArea className="flex-1">
        {isLoading ? (
          <div className="p-2 space-y-2">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : groupedConversations.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground text-sm">
            {searchQuery ? "No matches" : "No conversations"}
          </div>
        ) : (
          <div className="p-2">
            {groupedConversations.map((group) => (
              <div key={group.label} className="mb-3">
                <h3 className="px-2 py-1 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  {group.label}
                </h3>
                <div className="space-y-0.5">
                  {group.conversations.map((conv) => {
                    const config = modeConfig[conv.mode];
                    const ModeIcon = config.icon;
                    const isSelected = conv.id === selectedId;
                    const isHovered = conv.id === hoveredId;

                    return (
                      <div
                        key={conv.id}
                        onClick={() => onSelect(conv.id)}
                        onMouseEnter={() => setHoveredId(conv.id)}
                        onMouseLeave={() => setHoveredId(null)}
                        className={cn(
                          "group flex items-start gap-2 p-2 rounded-md cursor-pointer transition-colors",
                          isSelected
                            ? "bg-primary/10 border border-primary/30"
                            : "hover:bg-muted/50 border border-transparent"
                        )}
                      >
                        <ModeIcon
                          size={14}
                          className={cn(
                            "mt-0.5 shrink-0",
                            isSelected ? "text-primary" : config.color
                          )}
                        />
                        <div className="flex-1 min-w-0">
                          <p
                            className={cn(
                              "text-sm truncate",
                              isSelected ? "text-primary font-medium" : "text-foreground"
                            )}
                          >
                            {conv.title}
                          </p>
                          <p className="text-[10px] text-muted-foreground">
                            {conv.message_count} msgs · {formatDistanceToNow(new Date(conv.updated_at), { addSuffix: true })}
                          </p>
                        </div>
                        {onDelete && isHovered && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive"
                            onClick={(e) => {
                              e.stopPropagation();
                              onDelete(conv.id);
                            }}
                          >
                            <Trash2 size={12} />
                          </Button>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  );
};

export default ConversationsPanel;
