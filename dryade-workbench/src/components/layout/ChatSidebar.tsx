// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import ThemeToggle from "./ThemeToggle";
import {
  ArrowLeft,
  Plus,
  Search,
  X,
  MessageSquare,
  Users,
  GitBranch,
  Workflow,
  Trash2,
  Sparkles,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import type { Conversation, ChatMode } from "@/types/api";

const modeConfig: Record<ChatMode, { icon: typeof MessageSquare; color: string; label: string }> = {
  chat: { icon: MessageSquare, color: "text-muted-foreground", label: "Chat" },
  planner: { icon: GitBranch, color: "text-purple-500", label: "Planner" },
};

interface ChatSidebarProps {
  conversations: Conversation[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onDelete?: (id: string) => void;
  onBack: () => void;
  isLoading?: boolean;
}

// Group conversations by date - uses i18n keys for labels
const groupByDate = (conversations: Conversation[], t: (key: string) => string) => {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);
  const thisWeek = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);

  const groups: { label: string; conversations: Conversation[] }[] = [
    { label: t('sidebar.today'), conversations: [] },
    { label: t('sidebar.yesterday'), conversations: [] },
    { label: t('sidebar.thisWeek'), conversations: [] },
    { label: t('sidebar.older'), conversations: [] },
  ];

  conversations.forEach((conv) => {
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

const ChatSidebar = ({
  conversations,
  selectedId,
  onSelect,
  onNewChat,
  onDelete,
  onBack,
  isLoading = false,
}: ChatSidebarProps) => {
  const { t } = useTranslation('chat');
  const [searchQuery, setSearchQuery] = useState("");
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const filteredConversations = useMemo(() => {
    if (!searchQuery.trim()) return conversations;
    const query = searchQuery.toLowerCase();
    return conversations.filter((c) =>
      c.title.toLowerCase().includes(query) ||
      (c.mode && c.mode.toLowerCase().includes(query))
    );
  }, [conversations, searchQuery]);

  const groupedConversations = useMemo(
    () => groupByDate(filteredConversations, t),
    [filteredConversations, t]
  );

  if (isLoading) {
    return (
      <div className="h-full flex flex-col bg-sidebar">
        <div className="p-4 border-b border-sidebar-border">
          <Skeleton className="h-8 w-full" />
        </div>
        <div className="p-3 space-y-3" role="status" aria-label="Loading conversations">
          {[...Array(5)].map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-sidebar">
      {/* Header with Back Button */}
      <div className="p-4 border-b border-sidebar-border">
        <div className="flex items-center gap-2 mb-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={onBack}
            className="gap-2 text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft size={16} />
            <span className="text-sm">{t('sidebar.menu')}</span>
          </Button>
          <div className="flex-1" />
          <div className="flex items-center gap-1">
            <Sparkles size={14} className="text-primary" />
            <span className="text-sm font-semibold text-foreground">{t('sidebar.chat')}</span>
          </div>
        </div>

        {/* New Chat Button */}
        <Button
          onClick={onNewChat}
          className="w-full gap-2 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20"
          variant="outline"
        >
          <Plus size={16} />
          {t('sidebar.newChat')}
        </Button>
      </div>

      {/* Search */}
      <div className="p-3 border-b border-sidebar-border">
        <div className="relative">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('sidebar.searchPlaceholder')}
            aria-label="Search conversations"
            className="pl-9 pr-8 h-9 text-sm bg-sidebar-accent/50"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              aria-label="Clear search"
              className="absolute right-3 top-1/2 -translate-y-1/2 p-2 text-muted-foreground hover:text-foreground"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Conversation List */}
      <ScrollArea className="flex-1">
        <div className="p-2">
          {groupedConversations.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground text-sm">
              {searchQuery ? t('sidebar.noConversationsFound') : t('sidebar.noConversationsYet')}
            </div>
          ) : (
            groupedConversations.map((group) => (
              <div key={group.label} className="mb-4">
                <p className="px-2 py-1 text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  {group.label}
                </p>
                <div className="space-y-1">
                  {group.conversations.map((conv) => {
                    const config = modeConfig[conv.mode] ?? modeConfig['chat'];
                    const ModeIcon = config.icon;
                    const isSelected = conv.id === selectedId;
                    const isHovered = conv.id === hoveredId;

                    return (
                      <div
                        key={conv.id}
                        role="button"
                        tabIndex={0}
                        aria-current={isSelected ? "page" : undefined}
                        onClick={() => onSelect(conv.id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            onSelect(conv.id);
                          }
                        }}
                        onMouseEnter={() => setHoveredId(conv.id)}
                        onMouseLeave={() => setHoveredId(null)}
                        className={cn(
                          "group flex items-start gap-3 p-3 rounded-lg cursor-pointer transition-all duration-150 focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none",
                          isSelected
                            ? "bg-primary/10 border border-primary/30"
                            : "hover:bg-sidebar-accent border border-transparent"
                        )}
                      >
                        {/* Mode Icon */}
                        <div
                          className={cn(
                            "mt-0.5 p-1.5 rounded-md transition-colors",
                            isSelected ? "bg-primary/20" : "bg-muted/50"
                          )}
                        >
                          <ModeIcon
                            size={14}
                            className={cn(
                              isSelected ? "text-primary" : config.color
                            )}
                          />
                        </div>

                        {/* Content */}
                        <div className="flex-1 min-w-0">
                          <p
                            className={cn(
                              "text-sm font-medium truncate",
                              isSelected ? "text-primary" : "text-foreground"
                            )}
                          >
                            {conv.title}
                          </p>
                          <div className="flex items-center gap-2 mt-0.5">
                            <span className="text-xs text-muted-foreground">
                              {t('sidebar.messageCount', { count: conv.message_count })}
                            </span>
                            <span className="text-muted-foreground">·</span>
                            <span className="text-xs text-muted-foreground">
                              {formatDistanceToNow(new Date(conv.updated_at), {
                                addSuffix: true,
                              })}
                            </span>
                          </div>
                        </div>

                        {/* Delete Button */}
                        {onDelete && (
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label="Delete conversation"
                            className="h-7 w-7 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
                            onClick={(e) => {
                              e.stopPropagation();
                              onDelete(conv.id);
                            }}
                          >
                            <Trash2 size={14} />
                          </Button>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))
          )}
        </div>
      </ScrollArea>

      {/* Footer */}
      <div className="p-3 border-t border-sidebar-border">
        <div className="flex items-center justify-between px-2">
          <span className="text-xs text-muted-foreground">{t('sidebar.theme')}</span>
          <ThemeToggle />
        </div>
      </div>
    </div>
  );
};

export default ChatSidebar;
