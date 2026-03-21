// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// ChatHeader - Chat page header with title, connection status, mode selector,
// thinking toggle, search toggle, share button, and inline search bar.
// Extracted from ChatPage to reduce component size.

import React from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import ConnectionStatus from "@/components/chat/ConnectionStatus";
import ModeSelector from "@/components/chat/ModeSelector";
import { Search, X, Share2, MessageSquare, Brain, Download, Eye, EyeOff } from "lucide-react";
import type { ChatMode } from "@/types/api";

interface ChatHeaderProps {
  /** Current conversation title */
  conversationTitle: string;
  /** WebSocket connection state */
  connectionState: "connected" | "reconnecting" | "disconnected";
  /** WebSocket latency in ms */
  wsLatency?: number;
  /** Current reconnect attempt number */
  wsReconnectAttempt: number;
  /** Max reconnect attempts */
  wsMaxReconnects: number;
  /** Callback to manually reconnect */
  onReconnect: () => void;
  /** Current chat mode */
  chatMode: ChatMode;
  /** Callback to change chat mode */
  onChatModeChange: (mode: ChatMode) => void;
  /** Whether thinking/reasoning is enabled */
  enableThinking: boolean;
  /** Toggle thinking mode */
  onToggleThinking: () => void;
  /** Current event visibility level */
  eventVisibility: string;
  /** Toggle event visibility between named-steps and full-transparency */
  onToggleVisibility: () => void;
  /** Whether the search bar is open */
  searchOpen: boolean;
  /** Toggle search bar */
  onToggleSearch: () => void;
  /** Open the share dialog */
  onOpenShare: () => void;
  /** Current search query */
  searchQuery: string;
  /** Callback to change search query */
  onSearchQueryChange: (query: string) => void;
  /** Close search and clear query */
  onCloseSearch: () => void;
  /** Filtered messages count (shown when searching) */
  filteredCount?: number;
  /** Export conversation as markdown */
  onExport?: () => void;
}

/**
 * ChatHeader - Compact header bar for the chat page.
 *
 * Includes:
 * - Conversation title with connection status
 * - Mode selector (chat/orchestrate/planner)
 * - Thinking toggle button
 * - Search toggle button
 * - Share button
 * - Collapsible inline search bar
 */
export const ChatHeader = React.memo(function ChatHeader({
  conversationTitle,
  connectionState,
  wsLatency,
  wsReconnectAttempt,
  wsMaxReconnects,
  onReconnect,
  chatMode,
  onChatModeChange,
  enableThinking,
  onToggleThinking,
  eventVisibility,
  onToggleVisibility,
  searchOpen,
  onToggleSearch,
  onOpenShare,
  searchQuery,
  onSearchQueryChange,
  onCloseSearch,
  filteredCount,
  onExport,
}: ChatHeaderProps) {
  const { t } = useTranslation('chat');
  return (
    <>
      <header className="flex items-center justify-between px-4 py-2 border-b border-border bg-card/30">
        <div className="flex items-center gap-2 min-w-0">
          <MessageSquare size={16} className="text-primary shrink-0" />
          <span className="text-sm font-medium text-foreground truncate max-w-[200px]">
            {conversationTitle}
          </span>
          <ConnectionStatus
            status={connectionState}
            latencyMs={wsLatency}
            reconnectAttempt={wsReconnectAttempt}
            maxReconnects={wsMaxReconnects}
            onReconnect={onReconnect}
          />
        </div>

        <div className="flex items-center gap-1.5">
          <ModeSelector value={chatMode} onChange={onChatModeChange} />

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant={enableThinking ? "secondary" : "ghost"}
                size="icon-sm"
                className={`h-9 w-9 ${enableThinking ? "text-purple-500" : ""}`}
                onClick={onToggleThinking}
                aria-label={enableThinking ? "Disable reasoning" : "Enable reasoning"}
                aria-pressed={enableThinking}
              >
                <Brain size={14} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {enableThinking
                ? t('header.thinkingEnabled')
                : t('header.enableReasoning')}
            </TooltipContent>
          </Tooltip>

          {/* Full-Transparency Toggle */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant={eventVisibility === "full-transparency" ? "secondary" : "ghost"}
                size="icon-sm"
                className={`h-9 w-9 ${eventVisibility === "full-transparency" ? "text-blue-500" : ""}`}
                onClick={onToggleVisibility}
                aria-label={eventVisibility === "full-transparency" ? "Hide details" : "Show all details"}
                aria-pressed={eventVisibility === "full-transparency"}
              >
                {eventVisibility === "full-transparency" ? <Eye size={14} /> : <EyeOff size={14} />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {eventVisibility === "full-transparency"
                ? t('header.hideDetails', 'Hide details')
                : t('header.showAllDetails', 'Show all details')}
            </TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                className="h-9 w-9"
                onClick={onToggleSearch}
              >
                <Search size={14} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t('header.search')}</TooltipContent>
          </Tooltip>

          {onExport && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="h-9 w-9"
                  onClick={onExport}
                >
                  <Download size={14} />
                </Button>
              </TooltipTrigger>
              <TooltipContent>{t('header.exportConversation')}</TooltipContent>
            </Tooltip>
          )}

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                className="h-9 w-9"
                onClick={onOpenShare}
              >
                <Share2 size={14} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t('header.share')}</TooltipContent>
          </Tooltip>
        </div>
      </header>

      {/* Search Bar - Compact inline */}
      {searchOpen && (
        <div className="px-4 py-2 border-b border-border bg-muted/30 motion-safe:animate-fade-in">
          <div className="relative max-w-md">
            <Search
              size={12}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              value={searchQuery}
              onChange={(e) => onSearchQueryChange(e.target.value)}
              placeholder={t('header.searchPlaceholder')}
              className="h-8 pl-8 pr-8 text-sm"
              autoFocus
              aria-label="Search messages"
            />
            <button
              onClick={onCloseSearch}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground p-2"
              aria-label="Close search"
            >
              <X size={12} />
            </button>
            {filteredCount !== undefined && (
              <span className="absolute right-10 top-1/2 -translate-y-1/2 text-[10px] text-muted-foreground">
                {t('header.found', { count: filteredCount })}
              </span>
            )}
          </div>
        </div>
      )}
    </>
  );
});

export default ChatHeader;
