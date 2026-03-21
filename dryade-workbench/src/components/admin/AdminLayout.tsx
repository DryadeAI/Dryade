// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { useIsMobile } from "@/hooks/use-mobile";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  LayoutDashboard,
  Users,
  ShieldCheck,
  ScrollText,
  KeyRound,
  FolderSync,
  Puzzle,
  ChevronLeft,
  type LucideIcon,
} from "lucide-react";
import AdminDashboard from "./AdminDashboard";
import UsersPanel from "./UsersPanel";
import RolesPanel from "./RolesPanel";
import AuditLogPanel from "./AuditLogPanel";
import SsoPanel from "./SsoPanel";
import DirectoryPanel from "./DirectoryPanel";
import PluginsPanel from "./PluginsPanel";

type AdminTab = "overview" | "users" | "roles" | "audit" | "sso" | "directory" | "plugins";

interface TabConfig {
  id: AdminTab;
  labelKey: string;
  icon: LucideIcon;
}

const tabs: TabConfig[] = [
  { id: "overview", labelKey: "tabs.overview", icon: LayoutDashboard },
  { id: "users", labelKey: "tabs.users", icon: Users },
  { id: "roles", labelKey: "tabs.roles", icon: ShieldCheck },
  { id: "audit", labelKey: "tabs.auditLog", icon: ScrollText },
  { id: "sso", labelKey: "tabs.sso", icon: KeyRound },
  { id: "directory", labelKey: "tabs.directory", icon: FolderSync },
  { id: "plugins", labelKey: "tabs.plugins", icon: Puzzle },
];

export default function AdminLayout() {
  const { t } = useTranslation("admin");
  const { user } = useAuth();
  const isMobile = useIsMobile();
  const [activeTab, setActiveTab] = useState<AdminTab>("overview");
  const [mobileShowContent, setMobileShowContent] = useState(false);

  // Admin-only guard
  if (user?.role !== "admin") {
    return <Navigate to="/workspace/dashboard" replace />;
  }

  const renderContent = () => {
    switch (activeTab) {
      case "overview":
        return <AdminDashboard onTabChange={(tab) => setActiveTab(tab as AdminTab)} />;
      case "users":
        return <UsersPanel />;
      case "roles":
        return <RolesPanel />;
      case "audit":
        return <AuditLogPanel />;
      case "sso":
        return <SsoPanel />;
      case "directory":
        return <DirectoryPanel />;
      case "plugins":
        return <PluginsPanel />;
      default:
        return null;
    }
  };

  // Mobile layout
  if (isMobile) {
    if (!mobileShowContent) {
      return (
        <div className="h-full overflow-auto">
          <div className="px-4 pt-6 pb-4">
            <h1 className="text-2xl font-semibold">{t("dashboard.title")}</h1>
          </div>
          <nav className="px-3 space-y-0.5">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id);
                  setMobileShowContent(true);
                }}
                className={cn(
                  "w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors min-h-[40px]",
                  activeTab === tab.id
                    ? "bg-primary/10 text-primary font-semibold"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                )}
              >
                <tab.icon className="w-4 h-4 shrink-0" />
                <span>{t(tab.labelKey)}</span>
              </button>
            ))}
          </nav>
        </div>
      );
    }

    return (
      <div className="h-full overflow-auto">
        <div className="px-4 pt-4 pb-2">
          <button
            onClick={() => setMobileShowContent(false)}
            className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors mb-4"
          >
            <ChevronLeft className="w-4 h-4" />
            {t("dashboard.title")}
          </button>
          <h1 className="text-xl font-semibold">
            {t(tabs.find((tab) => tab.id === activeTab)?.labelKey ?? "")}
          </h1>
        </div>
        <div className="px-4 py-4">{renderContent()}</div>
      </div>
    );
  }

  // Desktop layout (same pattern as SettingsPage)
  return (
    <div className="h-full flex" data-testid="admin-container">
      {/* Content panel */}
      <div className="flex-1 overflow-auto">
        <div className="max-w-4xl mx-auto px-8 py-8">{renderContent()}</div>
      </div>

      {/* Right sidebar nav */}
      <div className="w-[220px] shrink-0 border-l border-border bg-muted/30 overflow-auto">
        <div className="px-4 pt-6 pb-2">
          <h2 className="text-lg font-semibold">{t("dashboard.title")}</h2>
        </div>
        <nav className="py-4 px-3 space-y-0.5">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors min-h-[40px]",
                activeTab === tab.id
                  ? "bg-primary/10 text-primary font-semibold"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
              )}
            >
              <tab.icon className="w-4 h-4 shrink-0" />
              <span>{t(tab.labelKey)}</span>
            </button>
          ))}
        </nav>
      </div>
    </div>
  );
}
