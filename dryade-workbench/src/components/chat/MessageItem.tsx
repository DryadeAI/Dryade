// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import React, { useState, useCallback, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { formatDistanceToNow } from "date-fns";
import {
  Bot,
  User,
  Loader2,
  Wrench,
  Copy,
  Check,
  Pencil,
  RefreshCw,
  ThumbsUp,
  ThumbsDown,
  MoreHorizontal,
  ChevronDown,
  ChevronRight,
  Trash2,
  Sparkles,
  Eye,
  Code as CodeIcon,
  CheckCircle2,
  XCircle,
  Play,
} from "lucide-react";
import type { AgentState } from "./ThinkingStream";
import type { PlanCardData, CodeExecuteResponse, CodeExecutionStatus } from "@/types/extended-api";
import ExpandableSources from "./ExpandableSources";
import { useCodeExecution } from "@/hooks/useCodeExecution";
import { CodeExecutionOutput } from "./CodeExecutionOutput";
import { ImageDisplay } from "./ImageDisplay";
import type { SourcedResult } from "./ExpandableSources";

export interface Message {
  id: string;
  role: "user" | "assistant" | "agent" | "tool";
  content: string;
  timestamp: Date;
  toolUse?: { name: string; status: "running" | "complete" };
  thinking?: string;
  feedback?: "up" | "down" | null;
  isEditing?: boolean;
  model?: string;
  agentName?: string; // For agent messages
  /** Persisted agent activity for augmented thinking display */
  agents?: Map<string, AgentState>;
  /** Phase 70-04: Plan data for planner mode - rendered as PlanCard */
  planData?: PlanCardData;
  /** Error message when LLM call fails - displayed inline with error styling */
  error?: string;
  /** Original user content that failed to send - used for retry */
  failedContent?: string;
  /** Phase 97-11: Enterprise search source attribution */
  sources?: SourcedResult[];
  /** Phase 97-11: Search duration in milliseconds */
  searchTimeMs?: number;
  /** Phase 228: Image content from MCP tool results or image generation */
  imageContent?: Array<{ data: string; mimeType: string; alt_text?: string }>;
}

interface MessageItemProps {
  message: Message;
  isGrouped: boolean;
  showAvatar: boolean;
  copiedId: string | null;
  editingInput: string;
  viewMode: "rendered" | "raw";
  onCopy: (content: string, id: string) => void;
  onEdit: (id: string) => void;
  onSaveEdit: (id: string) => void;
  onCancelEdit: (id: string) => void;
  onEditingInputChange: (value: string) => void;
  onRegenerate: (id: string) => void;
  onDelete: (id: string) => void;
  onFeedback: (id: string, type: "up" | "down") => void;
  onViewModeChange: (mode: "rendered" | "raw") => void;
  searchQuery?: string;
  /** Agent activity for augmented thinking display */
  agents?: Map<string, AgentState>;
  /** Whether this message is currently being streamed */
  isStreaming?: boolean;
  /** Callback to retry a failed message */
  onRetry?: () => void;
}

/** Collapsible wrapper that auto-expands when agents start running */
function ThinkingCollapsible({ autoExpand, children }: { autoExpand: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(autoExpand);
  useEffect(() => {
    if (autoExpand) setOpen(true);
  }, [autoExpand]);
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      {children}
    </Collapsible>
  );
}

/** Expandable tool call item showing name, args, and result */
function ToolCallItem({ tc }: { tc: { tool: string; args?: Record<string, unknown>; result?: string; status: "running" | "complete" | "error" } }) {
  const [open, setOpen] = useState(false);
  const hasDetail = tc.args && Object.keys(tc.args).length > 0 || tc.result;

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger aria-label={`Toggle tool details for ${tc.tool}`} className="flex items-center gap-1.5 w-full text-left py-0.5 hover:bg-muted/50 rounded px-1 -mx-1 text-[11px]">
        {hasDetail ? (
          <ChevronRight className={cn("h-2.5 w-2.5 shrink-0 transition-transform", open && "rotate-90")} />
        ) : (
          <span className="w-2.5" />
        )}
        <Wrench aria-hidden="true" className="h-2.5 w-2.5 text-muted-foreground shrink-0" />
        <span className="font-mono truncate flex-1">{tc.tool}</span>
        {tc.status === "running" && <Loader2 className="h-2.5 w-2.5 animate-spin shrink-0" />}
        {tc.status === "complete" && <CheckCircle2 className="h-2.5 w-2.5 text-green-500 shrink-0" />}
        {tc.status === "error" && <XCircle className="h-2.5 w-2.5 text-red-500 shrink-0" />}
      </CollapsibleTrigger>
      {hasDetail && (
        <CollapsibleContent className="pl-5 mt-0.5">
          {tc.args && Object.keys(tc.args).length > 0 && (
            <pre tabIndex={0} aria-label="Tool arguments" className="text-[11px] text-muted-foreground whitespace-pre-wrap font-mono bg-background/50 rounded px-1.5 py-1 max-h-16 overflow-auto mb-1">
              {JSON.stringify(tc.args, null, 2)}
            </pre>
          )}
          {tc.result && (
            <pre tabIndex={0} aria-label="Tool result" className="text-[11px] text-muted-foreground whitespace-pre-wrap font-mono bg-background/50 rounded px-1.5 py-1 max-h-24 overflow-auto">
              {tc.result}
            </pre>
          )}
        </CollapsibleContent>
      )}
    </Collapsible>
  );
}

/** Compact agent activity item for display inside thinking block */
function AgentActivityItem({ name, state }: { name: string; state: AgentState }) {
  const [open, setOpen] = useState(state.status === "running");

  const statusIcon = {
    idle: null,
    running: <Loader2 className="h-3 w-3 animate-spin text-blue-500" />,
    complete: <CheckCircle2 className="h-3 w-3 text-green-500" />,
    error: <XCircle className="h-3 w-3 text-red-500" />,
  }[state.status];

  const hasContent = state.content || state.toolCalls.length > 0;

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger aria-label={`Toggle agent details for ${name}`} className="flex items-center gap-1.5 w-full text-left py-1 hover:bg-muted/50 rounded px-1 -mx-1">
        <ChevronRight className={cn("h-3 w-3 transition-transform", open && "rotate-90")} />
        <Bot aria-hidden="true" className="h-3 w-3 text-muted-foreground" />
        <span className="text-[11px] font-medium flex-1 truncate">{name}</span>
        {state.task && (
          <span className="text-[11px] text-muted-foreground truncate max-w-[100px]">{state.task}</span>
        )}
        {statusIcon}
      </CollapsibleTrigger>
      {hasContent && (
        <CollapsibleContent className="pl-5 mt-0.5">
          {state.content && (
            <pre tabIndex={0} aria-label="Agent output" className="text-[11px] text-muted-foreground whitespace-pre-wrap font-mono bg-background/50 rounded px-1.5 py-1 max-h-24 overflow-auto">
              {state.content}
            </pre>
          )}
          {state.toolCalls.length > 0 && (
            <div className="mt-1 space-y-1">
              {state.toolCalls.map((tc, idx) => (
                <ToolCallItem key={`${tc.tool}-${idx}`} tc={tc} />
              ))}
            </div>
          )}
        </CollapsibleContent>
      )}
    </Collapsible>
  );
}

// Define role-based styles - compact for dense chat display
// Container widths optimized for readability (~65-70 chars per line)
const roleStyles = {
  user: {
    container: 'ml-auto max-w-[80%] lg:max-w-[65%]',
    bubble: 'bg-card/40 border-r-2 border-primary/50 rounded-lg',
    alignment: 'flex-row-reverse',
  },
  assistant: {
    container: 'mr-auto max-w-[85%] lg:max-w-[70%]',
    bubble: 'bg-card/60 border-l-2 border-primary/50 rounded-lg',
    alignment: 'flex-row',
    icon: Bot,
  },
  agent: {
    container: 'mr-auto max-w-[85%] lg:max-w-[70%]',
    bubble: 'border-l-2 border-accent-secondary/60 bg-card/40 rounded-lg',
    alignment: 'flex-row',
    icon: Sparkles,
  },
  tool: {
    container: 'mr-auto max-w-[85%] lg:max-w-[70%]',
    bubble: 'border-l-2 border-accent-tertiary/60 bg-card/30 rounded-lg font-mono text-xs',
    alignment: 'flex-row',
    icon: Wrench,
  },
} as const;

/** Code block component with syntax highlighting and copy button for ReactMarkdown */
interface CodeBlockProps {
  children: React.ReactNode;
  className?: string;
  onCopy: (code: string) => void;
  copied: boolean;
  onRun?: (code: string, language: string) => void;
  executionStatus?: CodeExecutionStatus;
  executionResult?: CodeExecuteResponse | null;
  executionError?: string | null;
}

/** Extract plain text from React children (handles rehype-highlight span tree) */
function extractPlainText(node: React.ReactNode): string {
  if (typeof node === "string") return node;
  if (typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(extractPlainText).join("");
  if (React.isValidElement(node)) {
    const el = node as React.ReactElement<{ children?: React.ReactNode }>;
    return extractPlainText(el.props.children);
  }
  return "";
}

const CodeBlock = (props: CodeBlockProps) => {
  const { children, className, onCopy, copied, onRun } = props;
  const runStatus = props.executionStatus;
  const runResult = props.executionResult;
  const runError = props.executionError;
  const { t } = useTranslation("chat");
  const langMatch = /language-(\w+)/.exec(className || "");
  const language = langMatch ? langMatch[1] : "code";
  const code = extractPlainText(children).replace(/\n$/, "");
  const canRun = onRun && ["python", "bash", "sh"].includes(language);

  return (
    <div className="relative group/code my-2">
      <div className="flex items-center justify-between text-[11px] text-muted-foreground bg-background/80 px-2 py-1 rounded-t-md border-b border-border">
        <span className="font-mono">{language}</span>
        <div className="flex items-center gap-1">
          {canRun && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1 text-xs"
              onClick={() => onRun(code, language)}
              disabled={runStatus === "running"}
            >
              {runStatus === "running" ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Play size={12} />
              )}
              {runStatus === "running"
                ? t("codeExecution.running")
                : t("codeExecution.run")}
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon-sm"
            className="h-7 w-7 opacity-0 group-hover/code:opacity-100 transition-opacity"
            aria-label="Copy code"
            onClick={() => onCopy(code)}
          >
            {copied ? (
              <Check size={10} className="text-success" />
            ) : (
              <Copy size={10} />
            )}
          </Button>
        </div>
      </div>
      <pre className="text-sm font-mono bg-background/80 p-3 rounded-b-md overflow-x-auto max-h-64 whitespace-pre">
        <code className={className}>{children}</code>
      </pre>
      {(runStatus === "running" || runResult || runError) && (
        <CodeExecutionOutput
          status={runStatus || "idle"}
          result={runResult || null}
          error={runError || null}
        />
      )}
    </div>
  );
};

/** Inline code styling */
const InlineCode = ({ children }: { children: React.ReactNode }) => (
  <code className="px-1.5 py-0.5 rounded bg-muted text-foreground font-mono text-[0.875em]">
    {children}
  </code>
);

const MessageItem = React.memo(function MessageItem({
  message,
  isGrouped,
  showAvatar,
  copiedId,
  editingInput,
  viewMode,
  onCopy,
  onEdit,
  onSaveEdit,
  onCancelEdit,
  onEditingInputChange,
  onRegenerate,
  onDelete,
  onFeedback,
  onViewModeChange,
  searchQuery,
  agents,
  isStreaming = false,
  onRetry,
}: MessageItemProps) {
  const { t } = useTranslation('chat');
  const [codeBlockCopied, setCodeBlockCopied] = useState<string | null>(null);
  const codeRun = useCodeExecution();

  // Format relative time (with fallback for invalid dates)
  const relativeTime = useMemo(() => {
    try {
      const date = message.timestamp instanceof Date ? message.timestamp : new Date(message.timestamp);
      if (isNaN(date.getTime())) return t('messages.justNow');
      return formatDistanceToNow(date, { addSuffix: true });
    } catch {
      return t('messages.justNow');
    }
  }, [message.timestamp]);

  const fullTimestamp = useMemo(() => {
    try {
      const date = message.timestamp instanceof Date ? message.timestamp : new Date(message.timestamp);
      if (isNaN(date.getTime())) return "";
      return date.toLocaleString();
    } catch {
      return "";
    }
  }, [message.timestamp]);

  // Check if content has code blocks (for view toggle)
  const hasCodeBlocks = useMemo(() => /```[\s\S]*?```/.test(message.content), [message.content]);

  const handleCopyCodeBlock = useCallback(async (code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      setCodeBlockCopied(code);
      setTimeout(() => setCodeBlockCopied(null), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  }, []);

  // Get role-specific styling
  const roleStyle = roleStyles[message.role];
  const RoleIcon = 'icon' in roleStyle ? roleStyle.icon : undefined;

  return (
    <div
      className={cn(
        "flex gap-2 motion-safe:animate-fade-in group",
        roleStyle.alignment,
        isGrouped && "mt-0.5",
        searchQuery && message.content.toLowerCase().includes(searchQuery.toLowerCase()) && "bg-primary/5 -mx-2 px-2 py-0.5 rounded"
      )}
      data-testid={`chat-${message.role}-message`}
    >
      {/* Avatar - visible size for better UX */}
      {showAvatar ? (
        <div
          className={cn(
            "w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5",
            message.role === "user" && "bg-secondary/60",
            message.role === "assistant" && "bg-primary/10",
            message.role === "agent" && "bg-accent-secondary/15",
            message.role === "tool" && "bg-accent-tertiary/15"
          )}
        >
          {message.role === "user" ? (
            <User size={16} className="text-muted-foreground" />
          ) : RoleIcon ? (
            <RoleIcon
              size={16}
              className={cn(
                message.role === "assistant" && "text-primary",
                message.role === "agent" && "text-accent-secondary",
                message.role === "tool" && "text-accent-tertiary"
              )}
            />
          ) : null}
        </div>
      ) : (
        <div className="w-8 shrink-0" /> // Spacer for alignment
      )}

      {/* Message Content */}
      <div
        className={cn(
          roleStyle.container,
          "space-y-1 relative",
          message.role === "user" && "text-right"
        )}
      >
        {/* Role/Model Badge - Only on first message in group for agent/tool messages (styling makes assistant obvious) */}
        {(message.role === "agent" || message.role === "tool") && showAvatar && (
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-medium text-foreground">
              {message.role === "agent" && (message.agentName || t('messages.agent'))}
              {message.role === "tool" && t('messages.toolOutput')}
            </span>
            {message.model && (
              <span className="text-[11px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-mono">
                {message.model}
              </span>
            )}
          </div>
        )}

        {/* Augmented Thinking Section - includes thinking text and agent activity */}
        {(() => {
          // Use prop agents (streaming) or fall back to persisted message.agents
          const displayAgents = agents || message.agents;
          const hasAgents = displayAgents && displayAgents.size > 0;
          const hasThinking = message.thinking;

          if (!hasThinking && !hasAgents) return null;
          if (message.role !== "assistant") return null;

          const hasRunningAgent = hasAgents && Array.from(displayAgents!.values()).some(a => a.status === "running");

          return (
            <ThinkingCollapsible autoExpand={isStreaming || hasRunningAgent}>
              <CollapsibleTrigger asChild>
                <button aria-label="Toggle thinking process" className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors">
                  <Sparkles size={10} />
                  <span>{t('messages.thinkingLabel')}</span>
                  {hasAgents && (
                    <span className="text-[11px] px-1 py-0.5 bg-muted rounded-full ml-1">
                      {t('messages.agentCount', { count: displayAgents!.size })}
                    </span>
                  )}
                  <ChevronDown size={10} className="transition-transform [[data-state=open]_&]:rotate-180" />
                </button>
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-1">
                <div className="bg-muted/30 rounded-md px-2 py-1.5 space-y-2">
                  {/* Agent Activity */}
                  {hasAgents && (
                    <div className="space-y-0.5">
                      {Array.from(displayAgents!.entries()).map(([name, state]) => (
                        <AgentActivityItem key={name} name={name} state={state} />
                      ))}
                    </div>
                  )}
                  {/* Reasoning/thinking text */}
                  {hasThinking && (
                    <pre tabIndex={0} aria-label="Thinking process" className="text-[11px] text-muted-foreground whitespace-pre-wrap font-mono bg-background/50 rounded px-2 py-1.5 max-h-48 overflow-auto leading-relaxed">
                      {message.thinking}
                    </pre>
                  )}
                </div>
              </CollapsibleContent>
            </ThinkingCollapsible>
          );
        })()}

        {/* Tool Use Indicator */}
        {message.toolUse && (
          <div
            className={cn(
              "inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-mono",
              message.toolUse.status === "running"
                ? "bg-primary/10 text-primary"
                : "bg-success/10 text-success"
            )}
          >
            {message.toolUse.status === "running" ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Wrench size={12} />
            )}
            {message.toolUse.name}
          </div>
        )}

        {/* Error indicator for failed LLM responses */}
        {message.error && (
          <div role="alert" className="flex items-center gap-1.5 text-destructive text-xs font-medium px-2 py-1 bg-destructive/10 rounded-md border border-destructive/20">
            <XCircle size={14} />
            <span>{t('messages.responseFailed')}</span>
            {onRetry && (
              <button
                onClick={onRetry}
                className="ml-2 inline-flex items-center gap-1 text-xs font-medium text-destructive hover:text-destructive/80 underline"
              >
                <RefreshCw size={12} />
                {t('messages.retry')}
              </button>
            )}
          </div>
        )}

        {/* Text Content */}
        {message.content && (
          <>
            {message.isEditing ? (
              <div className="space-y-2">
                <Input
                  value={editingInput}
                  onChange={(e) => onEditingInputChange(e.target.value)}
                  className="text-sm"
                  aria-label="Edit message"
                  autoFocus
                />
                <div className="flex gap-2 justify-end">
                  <Button size="sm" variant="ghost" onClick={() => onCancelEdit(message.id)}>
                    {t('messages.cancel')}
                  </Button>
                  <Button size="sm" onClick={() => onSaveEdit(message.id)}>
                    {t('messages.save')}
                  </Button>
                </div>
              </div>
            ) : (
              <div
                className={cn(
                  "rounded-lg overflow-hidden",
                  roleStyle.bubble
                )}
              >
                {/* View Mode Toggle - Persistent when has code blocks */}
                {hasCodeBlocks && message.role === "assistant" && (
                  <div className="flex items-center justify-end gap-1 px-3 pt-2 pb-1">
                    <div role="group" aria-label="View mode" className="flex items-center bg-muted/50 rounded-md p-0.5">
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button
                            onClick={() => onViewModeChange("rendered")}
                            aria-pressed={viewMode === "rendered"}
                            aria-label="Rendered view"
                            className={cn(
                              "p-1 rounded transition-colors",
                              viewMode === "rendered"
                                ? "bg-background text-foreground shadow-sm"
                                : "text-muted-foreground hover:text-foreground"
                            )}
                          >
                            <Eye size={12} />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent>{t('messages.renderedView')}</TooltipContent>
                      </Tooltip>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button
                            onClick={() => onViewModeChange("raw")}
                            aria-pressed={viewMode === "raw"}
                            aria-label="Raw code view"
                            className={cn(
                              "p-1 rounded transition-colors",
                              viewMode === "raw"
                                ? "bg-background text-foreground shadow-sm"
                                : "text-muted-foreground hover:text-foreground"
                            )}
                          >
                            <CodeIcon size={12} />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent>{t('messages.rawView')}</TooltipContent>
                      </Tooltip>
                    </div>
                  </div>
                )}

                <div className="px-3 py-2">
                  {viewMode === "raw" ? (
                    <pre className="text-[13px] font-mono whitespace-pre-wrap break-words leading-relaxed">
                      {message.content}
                      {isStreaming && <span className="streaming-cursor" aria-hidden="true" />}
                    </pre>
                  ) : (
                    <div className={cn("prose prose-sm dark:prose-invert max-w-none text-[13px] leading-relaxed prose-p:my-1.5 prose-headings:my-2 prose-headings:text-sm prose-ul:my-1 prose-ol:my-1 prose-li:my-0 prose-pre:my-0 prose-pre:p-0 prose-pre:bg-transparent", isStreaming && "streaming-content")}>
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      rehypePlugins={[rehypeHighlight]}
                      components={{
                        // Custom code block with syntax highlighting, copy, and run button
                        code: ({ className, children, ...props }) => {
                          const isBlock = Boolean(className);
                          if (!isBlock) {
                            return <InlineCode>{children}</InlineCode>;
                          }
                          const code = extractPlainText(children).replace(/\n$/, "");
                          return (
                            <CodeBlock
                              className={className}
                              onCopy={handleCopyCodeBlock}
                              copied={codeBlockCopied === code}
                              onRun={message.role === "assistant"
                                ? (c, lang) => codeRun.execute(c, lang as "python" | "bash" | "sh")
                                : undefined}
                              executionStatus={codeRun.status}
                              executionResult={codeRun.result}
                              executionError={codeRun.error}
                              {...props}
                            >
                              {children}
                            </CodeBlock>
                          );
                        },
                        // Remove the wrapper pre from react-markdown (we handle it in CodeBlock)
                        pre: ({ children }) => <>{children}</>,
                        // Style links
                        a: ({ href, children }) => (
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary hover:underline"
                          >
                            {children}
                          </a>
                        ),
                        // Style tables
                        table: ({ children }) => (
                          <div className="overflow-x-auto my-2">
                            <table className="min-w-full text-sm border-collapse border border-border rounded">
                              {children}
                            </table>
                          </div>
                        ),
                        th: ({ children }) => (
                          <th className="border border-border bg-muted/50 px-3 py-1.5 text-left font-medium">
                            {children}
                          </th>
                        ),
                        td: ({ children }) => (
                          <td className="border border-border px-3 py-1.5">{children}</td>
                        ),
                        // Style blockquotes
                        blockquote: ({ children }) => (
                          <blockquote className="border-l-2 border-primary/50 pl-3 my-2 italic text-muted-foreground">
                            {children}
                          </blockquote>
                        ),
                        // Style unordered lists
                        ul: ({ children }) => (
                          <ul className="list-disc list-outside pl-5 my-1 space-y-0.5">
                            {children}
                          </ul>
                        ),
                        // Style ordered lists
                        ol: ({ children }) => (
                          <ol className="list-decimal list-outside pl-5 my-1 space-y-0.5">
                            {children}
                          </ol>
                        ),
                      }}
                    >
                      {message.content}
                    </ReactMarkdown>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Enterprise search sources -- below the message bubble */}
            {message.sources && message.sources.length > 0 && (
              <ExpandableSources
                sources={message.sources}
                searchTimeMs={message.searchTimeMs}
              />
            )}

            {/* Inline images from image generation or tool results */}
            {message.imageContent && message.imageContent.length > 0 && (
              <div className="mt-3">
                <ImageDisplay images={message.imageContent} />
              </div>
            )}
          </>
        )}

        {/* Message Actions - Hidden by default, visible on hover */}
        {!message.isEditing && message.content && (
          <div
            className={cn(
              "flex items-center gap-1 transition-opacity duration-150",
              "opacity-0 group-hover:opacity-100 focus-within:opacity-100",
              message.role === "user" ? "justify-end" : "justify-start"
            )}
          >
            {/* Feedback buttons - only for assistant, appear on hover */}
            {message.role === "assistant" && (
              <div className="flex items-center gap-0.5">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className={cn("h-6 w-6", message.feedback === "up" && "text-success bg-success/10")}
                      onClick={() => onFeedback(message.id, "up")}
                      aria-label="Good response"
                    >
                      <ThumbsUp size={12} />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>{t('messages.goodResponse')}</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className={cn("h-6 w-6", message.feedback === "down" && "text-destructive bg-destructive/10")}
                      onClick={() => onFeedback(message.id, "down")}
                      aria-label="Bad response"
                    >
                      <ThumbsDown size={12} />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>{t('messages.badResponse')}</TooltipContent>
                </Tooltip>
              </div>
            )}

            {/* Menu button with context-appropriate options */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="h-6 w-6"
                  aria-label="Message options"
                >
                  <MoreHorizontal size={12} />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align={message.role === "user" ? "end" : "start"}>
                <DropdownMenuItem onClick={() => onCopy(message.content, message.id)}>
                  {copiedId === message.id ? <Check size={14} /> : <Copy size={14} />}
                  {copiedId === message.id ? t('messages.copied') : t('messages.copy')}
                </DropdownMenuItem>
                {message.role === "user" && (
                  <DropdownMenuItem onClick={() => onEdit(message.id)}>
                    <Pencil size={14} />
                    {t('messages.edit')}
                  </DropdownMenuItem>
                )}
                {message.role === "assistant" && (
                  <DropdownMenuItem onClick={() => onRegenerate(message.id)}>
                    <RefreshCw size={14} />
                    {t('messages.regenerate')}
                  </DropdownMenuItem>
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={() => onDelete(message.id)}
                  className="text-destructive focus:text-destructive"
                >
                  <Trash2 size={14} />
                  {t('messages.delete')}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Relative Timestamp with full on hover - smaller and more subtle */}
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="text-[11px] text-muted-foreground/70 ml-2 cursor-default">
                  {relativeTime}
                </span>
              </TooltipTrigger>
              <TooltipContent>{fullTimestamp}</TooltipContent>
            </Tooltip>
          </div>
        )}
      </div>
    </div>
  );
});

export default MessageItem;
