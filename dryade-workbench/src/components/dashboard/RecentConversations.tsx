// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import { MessageSquare, Anchor, Brain, RefreshCw, ArrowRight } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDistanceToNow } from "date-fns";
import type { Conversation, ChatMode } from "@/types/api";

interface RecentConversationsProps {
  conversations?: Conversation[];
  isLoading?: boolean;
}

const modeConfig: Record<ChatMode, { icon: typeof MessageSquare; color: string; label: string }> = {
  chat: { icon: MessageSquare, color: "text-muted-foreground", label: "Chat" },
  planner: { icon: Brain, color: "text-accent-secondary", label: "Planner" },
};

const RecentConversations = ({ conversations = [], isLoading = false }: RecentConversationsProps) => {
  if (isLoading) {
    return (
      <div className="glass-card p-5">
        <div className="flex items-center justify-between mb-4">
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-4 w-16" />
        </div>
        <div className="space-y-2">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="flex items-center gap-3 p-2">
              <Skeleton className="w-5 h-5 rounded" />
              <div className="flex-1">
                <Skeleton className="h-4 w-3/4 mb-1" />
                <Skeleton className="h-3 w-1/2" />
              </div>
              <Skeleton className="h-4 w-12" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  const isEmpty = conversations.length === 0;

  return (
    <div className="glass-card p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-foreground">Recent Conversations</h2>
        <Link
          to="/workspace/chat"
          className="text-xs text-muted-foreground hover:text-primary flex items-center gap-1 transition-colors"
        >
          View all <ArrowRight size={10} />
        </Link>
      </div>

      {isEmpty ? (
        <div className="text-center py-8">
          <MessageSquare size={32} className="mx-auto text-muted-foreground/50 mb-2" />
          <p className="text-sm text-muted-foreground">No conversations yet</p>
          <Link
            to="/workspace/chat"
            className="text-xs text-primary hover:underline mt-1 inline-block"
          >
            Start your first chat
          </Link>
        </div>
      ) : (
        <div className="space-y-1">
          {conversations.map((conv) => {
            const mode = modeConfig[conv.mode];
            const ModeIcon = mode.icon;
            const timeAgo = formatDistanceToNow(new Date(conv.updated_at), { addSuffix: true });

            return (
              <Link
                key={conv.id}
                to={`/workspace/chat?id=${conv.id}`}
                className="flex items-center gap-3 p-2 rounded-lg hover:bg-secondary/50 transition-colors group"
              >
                <ModeIcon size={16} className={cn(mode.color)} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate group-hover:text-primary transition-colors">
                    {conv.title || "Untitled conversation"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {conv.message_count} messages · {mode.label}
                  </p>
                </div>
                <span className="text-xs text-muted-foreground whitespace-nowrap">
                  {timeAgo}
                </span>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default RecentConversations;
