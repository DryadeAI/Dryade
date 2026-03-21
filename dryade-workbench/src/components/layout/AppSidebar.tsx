// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import iconLogo from "@/assets/icon-logo.svg";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import ThemeToggle from "./ThemeToggle";
import LanguageSwitcher from "./LanguageSwitcher";
import { useLocalStorage } from "@/hooks/useLocalStorage";
import { usePluginUI } from "@/hooks/usePluginUI";
import { useAuth } from "@/contexts/AuthContext";
import {
  Activity,
  BarChart3,
  LayoutDashboard,
  Workflow,
  MessageSquare,
  Settings,
  LogOut,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Puzzle,
  Bot,
  BookOpen,
  Factory,
  Menu,
  X,
  Loader2,
  DollarSign,
  HelpCircle,
  Timer,
  Shield,
  type LucideIcon,
} from "lucide-react";
import React, { useState, useEffect, useCallback } from "react";
import { resolvePluginIcon } from "@/lib/plugin-icons";

// ── Navigation structure ──────────────────────────────────────

type NavItem = { href: string; icon: LucideIcon; labelKey: string };

const primaryItemsMap: Record<string, NavItem> = {
  "/workspace/chat": { href: "/workspace/chat", icon: MessageSquare, labelKey: "nav.chat" },
  "/workspace/dashboard": { href: "/workspace/dashboard", icon: LayoutDashboard, labelKey: "nav.dashboard" },
  "/workspace/agents": { href: "/workspace/agents", icon: Bot, labelKey: "nav.agents" },
  "/workspace/workflows": { href: "/workspace/workflows", icon: Workflow, labelKey: "nav.workflows" },
  "/workspace/knowledge": { href: "/workspace/knowledge", icon: BookOpen, labelKey: "nav.knowledge" },
  "/workspace/factory": { href: "/workspace/factory", icon: Factory, labelKey: "nav.factory" },
};

const defaultPrimaryOrder = [
  "/workspace/chat",
  "/workspace/dashboard",
  "/workspace/agents",
  "/workspace/workflows",
  "/workspace/knowledge",
  "/workspace/factory",
];

const systemItems: NavItem[] = [
  { href: "/workspace/loops", icon: Timer, labelKey: "nav.loops" },
  { href: "/workspace/health", icon: Activity, labelKey: "nav.health" },
  { href: "/workspace/metrics", icon: BarChart3, labelKey: "nav.metrics" },
  { href: "/workspace/cost-tracker", icon: DollarSign, labelKey: "nav.costTracker" },
  { href: "/workspace/clarify-preferences", icon: HelpCircle, labelKey: "nav.clarifyPreferences" },
];

const adminItem: NavItem = { href: "/workspace/admin", icon: Shield, labelKey: "nav.admin" };

const accountItems: NavItem[] = [
  { href: "/workspace/plugins", icon: Puzzle, labelKey: "nav.plugins" },
  { href: "/workspace/settings", icon: Settings, labelKey: "nav.settings" },
];

// ── Component ─────────────────────────────────────────────────

interface AppSidebarProps {
  /** When provided by WorkspaceLayout top bar, use this as the mobile open state */
  externalMobileOpen?: boolean;
  /** Callback to close the externally-controlled mobile sidebar */
  onExternalMobileClose?: () => void;
}

const AppSidebar = React.memo(function AppSidebar({
  externalMobileOpen,
  onExternalMobileClose,
}: AppSidebarProps) {
  const location = useLocation();
  const { t } = useTranslation();
  const { user } = useAuth();
  const [collapsed, setCollapsed] = useLocalStorage("sidebar-collapsed", false);
  const [mobileOpenInternal, setMobileOpenInternal] = useState(false);

  // Use external state if provided, otherwise fall back to internal
  const mobileOpen = externalMobileOpen !== undefined ? externalMobileOpen : mobileOpenInternal;
  const setMobileOpen = (value: boolean) => {
    if (externalMobileOpen !== undefined) {
      if (!value) onExternalMobileClose?.();
    } else {
      setMobileOpenInternal(value);
    }
  };
  const [navOrder, setNavOrder] = useLocalStorage<string[]>("sidebar-nav-order", defaultPrimaryOrder);
  const [draggedHref, setDraggedHref] = useState<string | null>(null);
  const [dragOverHref, setDragOverHref] = useState<string | null>(null);

  // Foldable section states
  const [observabilityOpen, setObservabilityOpen] = useLocalStorage("sidebar-observability-open", true);
  const [pluginsOpen, setPluginsOpen] = useLocalStorage("sidebar-plugins-open", true);
  const [accountOpen, setAccountOpen] = useLocalStorage("sidebar-account-open", true);

  // Expose sidebar width as CSS variable for content centering
  useEffect(() => {
    document.documentElement.style.setProperty(
      "--sidebar-width",
      collapsed ? "4rem" : "13rem"
    );
  }, [collapsed]);

  // Plugin UIs for dynamic sidebar items
  const { uiPlugins, isLoading: pluginsLoading, newlyAddedPlugins, clearNewPlugin } = usePluginUI();

  const isActive = (href: string) =>
    location.pathname === href || location.pathname.startsWith(href + "/");

  // Ordered primary items from persisted order
  const orderedPrimaryItems = (navOrder ?? defaultPrimaryOrder)
    .filter((href) => primaryItemsMap[href])
    .map((href) => primaryItemsMap[href]);

  // ── Drag and Drop ─────────────────────────────────────────

  const handleDragStart = useCallback((href: string) => {
    setDraggedHref(href);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent, targetHref: string) => {
    e.preventDefault();
    setDragOverHref(targetHref);
  }, []);

  const handleDrop = useCallback((targetHref: string) => {
    if (!draggedHref || draggedHref === targetHref) {
      setDraggedHref(null);
      setDragOverHref(null);
      return;
    }

    const currentOrder = navOrder ?? defaultPrimaryOrder;
    const fromIndex = currentOrder.indexOf(draggedHref);
    const toIndex = currentOrder.indexOf(targetHref);
    if (fromIndex === -1 || toIndex === -1) return;

    const newOrder = [...currentOrder];
    newOrder.splice(fromIndex, 1);
    newOrder.splice(toIndex, 0, draggedHref);
    setNavOrder(newOrder);
    setDraggedHref(null);
    setDragOverHref(null);
  }, [draggedHref, navOrder, setNavOrder]);

  const handleDragEnd = useCallback(() => {
    setDraggedHref(null);
    setDragOverHref(null);
  }, []);

  // ── Helpers ──────────────────────────────────────────────

  const getInitials = (name?: string | null) => {
    if (!name) return "??";
    return name.split(" ").filter(Boolean).map((n) => n[0]).join("").toUpperCase().slice(0, 2) || "??";
  };

  // ── Render helpers ────────────────────────────────────────

  const renderItem = (item: NavItem, draggable = false) => {
    const active = isActive(item.href);
    const isDragging = draggedHref === item.href;
    const isDragOver = dragOverHref === item.href && draggedHref !== item.href;
    const label = t(item.labelKey);

    return (
      <Tooltip key={item.href}>
        <TooltipTrigger asChild>
          <Link
            to={item.href}
            onClick={() => setMobileOpen(false)}
            aria-current={active ? "page" : undefined}
            data-testid={`sidebar-nav-${item.href.split("/").pop()}-link`}
            draggable={draggable && !collapsed}
            onDragStart={draggable ? () => handleDragStart(item.href) : undefined}
            onDragOver={draggable ? (e) => handleDragOver(e, item.href) : undefined}
            onDrop={draggable ? () => handleDrop(item.href) : undefined}
            onDragEnd={draggable ? handleDragEnd : undefined}
            className={cn(
              "relative flex items-center gap-3 px-3 py-2 rounded-md text-sm motion-safe:transition-all motion-safe:duration-200",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
              active
                ? "bg-primary/10 text-sidebar-accent-foreground font-medium"
                : "text-sidebar-foreground/60 hover:bg-muted/40 hover:text-sidebar-foreground",
              isDragging && "opacity-40",
              isDragOver && "ring-1 ring-primary/40 bg-primary/5"
            )}
            aria-label={collapsed ? label : undefined}
          >
            {/* Active indicator bar */}
            {active && (
              <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-full bg-primary" />
            )}
            <item.icon size={18} className="text-[hsl(var(--emerald-400))]" aria-hidden="true" />
            {!collapsed && <span className={cn(active && "glow-text-sm")}>{label}</span>}
          </Link>
        </TooltipTrigger>
        {collapsed && (
          <TooltipContent side="right">{label}</TooltipContent>
        )}
      </Tooltip>
    );
  };

  const renderFoldableSection = (
    labelKey: string,
    items: NavItem[],
    isOpen: boolean,
    setIsOpen: (v: boolean) => void
  ) => {
    const label = t(labelKey);
    if (collapsed) {
      return (
        <div key={`section-${labelKey}`} className="space-y-0.5">
          <div className="my-2 px-3">
            <div className="border-t border-border/40" />
          </div>
          {items.map((item) => renderItem(item))}
        </div>
      );
    }

    return (
      <Collapsible key={`section-${labelKey}`} open={isOpen} onOpenChange={setIsOpen}>
        <div className="my-2 px-3">
          <div className="border-t border-border/40" />
        </div>
        <CollapsibleTrigger className="flex items-center justify-between w-full px-3 py-1 group cursor-pointer">
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest">
            {label}
          </p>
          <ChevronDown
            size={12}
            aria-hidden="true"
            className={cn(
              "text-muted-foreground/40 motion-safe:transition-transform motion-safe:duration-200",
              !isOpen && "-rotate-90"
            )}
          />
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-0.5">
          {items.map((item) => renderItem(item))}
        </CollapsibleContent>
      </Collapsible>
    );
  };

  // ── Sidebar content ───────────────────────────────────────

  const sidebarContent = (
    <>
      {/* Logo + Collapse toggle at top */}
      <div className="p-4 border-b border-border/40 flex items-center justify-between">
        <Link to="/workspace" className="flex items-center gap-2">
          <img src={iconLogo} alt="Dryade" className="w-8 h-8 dark:brightness-100 brightness-0" />
          {!collapsed && (
            <span className="font-semibold text-sidebar-foreground">
              Dryade<span className="text-primary">App</span>
            </span>
          )}
        </Link>
        <div className="flex items-center gap-1">
          {/* Mobile close button */}
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden h-7 w-7"
            onClick={() => setMobileOpen(false)}
            aria-label={t('actions.closeMenu', 'Close menu')}
          >
            <X size={16} aria-hidden="true" />
          </Button>
          {/* Desktop collapse toggle */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setCollapsed(!collapsed)}
                className="hidden md:flex h-7 w-7 text-muted-foreground hover:text-foreground"
                aria-label={collapsed ? t('actions.expand') : t('actions.collapse')}
              >
                {collapsed ? (
                  <ChevronRight size={16} aria-hidden="true" />
                ) : (
                  <ChevronLeft size={16} aria-hidden="true" />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent side={collapsed ? "right" : "bottom"}>
              {collapsed ? t('actions.expand') : t('actions.collapse')}
            </TooltipContent>
          </Tooltip>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto" aria-label="Workspace navigation" data-testid="sidebar-nav">
        {/* Primary — draggable */}
        {orderedPrimaryItems.map((item) => renderItem(item, true))}

        {/* Observability — foldable */}
        {renderFoldableSection("sections.observability", systemItems, observabilityOpen, setObservabilityOpen)}

        {/* Admin — only for admin users */}
        {user?.role === "admin" && (
          <div className="space-y-0.5">
            <div className="my-2 px-3">
              <div className="border-t border-border/40" />
            </div>
            {renderItem(adminItem)}
          </div>
        )}

        {/* Dynamic Plugin UIs */}
        {pluginsLoading && !uiPlugins.length && (
          <div className="px-3 py-2" role="status" aria-label={t('status.loadingPlugins', 'Loading plugins')}>
            <Loader2 size={14} className="motion-safe:animate-spin text-muted-foreground" aria-hidden="true" />
          </div>
        )}
        {uiPlugins.length > 0 && (
          <Collapsible key="section-plugins" open={pluginsOpen} onOpenChange={setPluginsOpen}>
            <div className="my-2 px-3">
              <div className="border-t border-border/40" />
            </div>
            {!collapsed && (
              <CollapsibleTrigger className="flex items-center justify-between w-full px-3 py-1 group cursor-pointer">
                <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest">
                  {t("sections.plugins")}
                </p>
                <ChevronDown
                  size={12}
                  aria-hidden="true"
                  className={cn(
                    "text-muted-foreground/40 motion-safe:transition-transform motion-safe:duration-200",
                    !pluginsOpen && "-rotate-90"
                  )}
                />
              </CollapsibleTrigger>
            )}
            <CollapsibleContent className="space-y-0.5">
              {uiPlugins.map((plugin) => {
                const pluginPath = `/workspace/plugins/${plugin.name}`;
                const iconName = plugin.sidebarItem?.icon || plugin.manifest?.icon;
                const IconComponent = resolvePluginIcon(iconName);
                const label = plugin.sidebarItem?.label || plugin.name;
                const active = isActive(pluginPath);
                const isNew = newlyAddedPlugins.has(plugin.name);

                return (
                  <Tooltip key={pluginPath}>
                    <TooltipTrigger asChild>
                      <Link
                        to={pluginPath}
                        onClick={() => {
                          setMobileOpen(false);
                          if (isNew) clearNewPlugin(plugin.name);
                        }}
                        aria-current={active ? "page" : undefined}
                        className={cn(
                          "relative flex items-center gap-3 px-3 py-2 rounded-md text-sm motion-safe:transition-all motion-safe:duration-200",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
                          active
                            ? "bg-primary/10 text-sidebar-accent-foreground font-medium"
                            : "text-sidebar-foreground/60 hover:bg-muted/40 hover:text-sidebar-foreground"
                        )}
                        aria-label={collapsed ? label : undefined}
                      >
                        {active && (
                          <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-full bg-primary" />
                        )}
                        <IconComponent size={18} className="text-[hsl(var(--emerald-400))] shrink-0" aria-hidden="true" />
                        {!collapsed && (
                          <span className={cn("flex-1 min-w-0 truncate", active && "glow-text-sm")}>
                            {label}
                          </span>
                        )}
                        {!collapsed && isNew && (
                          <span className="shrink-0 px-1 py-0.5 text-[9px] font-bold uppercase tracking-wide rounded bg-primary/20 text-primary leading-none">
                            NEW
                          </span>
                        )}
                      </Link>
                    </TooltipTrigger>
                    {collapsed && (
                      <TooltipContent side="right">
                        <span>{label}</span>
                        {isNew && (
                          <span className="ml-1.5 px-1 py-0.5 text-[9px] font-bold uppercase tracking-wide rounded bg-primary/20 text-primary leading-none">
                            NEW
                          </span>
                        )}
                      </TooltipContent>
                    )}
                  </Tooltip>
                );
              })}
            </CollapsibleContent>
          </Collapsible>
        )}

        {/* Account — foldable */}
        {renderFoldableSection("sections.account", accountItems, accountOpen, setAccountOpen)}
      </nav>

      {/* Bottom: Language + Theme + Avatar with inline Sign out */}
      <div className="p-3 border-t border-border/40 space-y-2 pwa-safe-bottom">
        {/* Language Switcher */}
        <div className="flex items-center justify-between px-2">
          {!collapsed && (
            <span className="text-xs text-muted-foreground">{t('language')}</span>
          )}
          <LanguageSwitcher collapsed={collapsed} />
        </div>

        {/* Theme Toggle */}
        <div className="flex items-center justify-between px-2">
          {!collapsed && (
            <span className="text-xs text-muted-foreground">{t('theme')}</span>
          )}
          <ThemeToggle />
        </div>

        {/* User Avatar + Sign out on same line */}
        <div className="group relative flex items-center gap-2 px-2 py-2 rounded-md hover:bg-sidebar-accent motion-safe:transition-all overflow-hidden">
          <Link
            to="/workspace/settings"
            onClick={() => setMobileOpen(false)}
            className="flex items-center gap-3 min-w-0 flex-1"
          >
            <Avatar className="h-8 w-8 shrink-0">
              <AvatarFallback
                className="text-xs font-medium bg-primary/20 text-primary"
                style={user?.preferences?.avatar_color ? {
                  backgroundColor: `${user.preferences.avatar_color as string}20`,
                  color: user.preferences.avatar_color as string,
                } : undefined}
              >
                {getInitials(user?.display_name || user?.email)}
              </AvatarFallback>
            </Avatar>
            {!collapsed && (
              <div className="flex-1 min-w-0 motion-safe:transition-all motion-safe:duration-300 group-hover:opacity-0 group-hover:-translate-x-4">
                <p className="text-sm font-medium text-sidebar-foreground truncate">
                  {user?.display_name || user?.email?.split("@")[0] || "User"}
                </p>
                <p className="text-[10px] text-muted-foreground truncate">
                  {user?.email || ""}
                </p>
              </div>
            )}
          </Link>
          {/* Sign out slides in on hover or focus-within */}
          {!collapsed && (
            <Link
              to="/"
              onClick={() => setMobileOpen(false)}
              className="absolute right-2 flex items-center gap-2 opacity-0 translate-x-4 group-hover:opacity-100 group-hover:translate-x-0 focus-visible:opacity-100 focus-visible:translate-x-0 motion-safe:transition-all motion-safe:duration-300 text-sm text-muted-foreground hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 rounded-md px-1"
              aria-label={t('actions.signOut')}
            >
              <span>{t('actions.signOut')}</span>
              <LogOut size={16} aria-hidden="true" />
            </Link>
          )}
          {collapsed && (
            <Link
              to="/"
              onClick={() => setMobileOpen(false)}
              className="shrink-0 text-muted-foreground hover:text-destructive motion-safe:transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 rounded-md"
              aria-label={t('actions.signOut')}
            >
              <LogOut size={16} aria-hidden="true" />
            </Link>
          )}
        </div>
      </div>
    </>
  );

  return (
    <>
      {/* Mobile Menu Button — only shown when NOT using the WorkspaceLayout top bar
          (i.e., when externalMobileOpen is not provided by parent) */}
      {externalMobileOpen === undefined && (
        <Button
          variant="ghost"
          size="icon"
          className="fixed top-4 left-4 z-50 md:hidden min-h-[44px] min-w-[44px]"
          onClick={() => setMobileOpenInternal(true)}
          aria-label={t('actions.openMenu', 'Open menu')}
        >
          <Menu size={20} aria-hidden="true" />
        </Button>
      )}

      {/* Mobile Overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-background/80 backdrop-blur-sm z-40 md:hidden"
          onClick={() => setMobileOpen(false)}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setMobileOpen(false);
            }
          }}
          role="button"
          tabIndex={0}
          aria-label={t('actions.closeSidebar', 'Close sidebar')}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          "h-screen flex flex-col bg-sidebar border-r border-border/40 motion-safe:transition-all motion-safe:duration-300",
          "hidden md:flex",
          collapsed ? "w-16" : "w-52",
          "bg-gradient-to-b from-sidebar via-sidebar to-background"
        )}
        aria-label="Main navigation"
      >
        {sidebarContent}
      </aside>

      {/* Mobile Sidebar */}
      <aside
        id="mobile-sidebar"
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-64 flex flex-col bg-gradient-to-b from-sidebar via-sidebar to-background border-r border-border/40 motion-safe:transition-transform motion-safe:duration-300 md:hidden",
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        )}
        aria-label="Mobile navigation"
        aria-hidden={!mobileOpen}
        {...(!mobileOpen && { tabIndex: -1 })}
      >
        {sidebarContent}
      </aside>
    </>
  );
});

export default AppSidebar;
