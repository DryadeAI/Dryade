// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Users, ShieldCheck, ScrollText, KeyRound, FolderSync, AlertTriangle } from "lucide-react";
import { adminApi } from "@/services/api/admin";
import { fetchWithAuth } from "@/services/apiClient";

interface AdminDashboardProps {
  onTabChange: (tab: string) => void;
}

export default function AdminDashboard({ onTabChange }: AdminDashboardProps) {
  const { t } = useTranslation("admin");

  // Use core /users endpoint (always available) with fallback to rights_basic
  const { data: usersData, isLoading: usersLoading, error: usersError } = useQuery({
    queryKey: ["admin", "users-count"],
    queryFn: async () => {
      try {
        return await adminApi.listUsers({ per_page: 1 });
      } catch {
        // Community mode: rights_basic not loaded, fall back to core endpoint
        const users = await fetchWithAuth<{ id: string }[]>("/users");
        return { users: [], total: Array.isArray(users) ? users.length : 0 };
      }
    },
  });

  const { data: rolesData, isLoading: rolesLoading } = useQuery({
    queryKey: ["admin", "roles-count"],
    queryFn: async () => {
      try {
        return await adminApi.listRoles();
      } catch {
        // Community mode: no RBAC plugin, return empty
        return { roles: [] };
      }
    },
  });

  const { data: auditData, isLoading: auditLoading } = useQuery({
    queryKey: ["admin", "audit-count"],
    queryFn: async () => {
      try {
        return await adminApi.queryCoreAudit({ per_page: 1 });
      } catch {
        return { entries: [], total: 0 };
      }
    },
  });

  const hasError = usersError;
  const isLoading = usersLoading || rolesLoading || auditLoading;

  const stats = [
    {
      title: t("dashboard.totalUsers"),
      value: usersData?.total ?? 0,
      icon: Users,
      loading: usersLoading,
    },
    {
      title: t("dashboard.totalRoles"),
      value: rolesData?.roles?.length ?? 0,
      icon: ShieldCheck,
      loading: rolesLoading,
    },
    {
      title: t("dashboard.auditEvents"),
      value: auditData?.total ?? 0,
      icon: ScrollText,
      loading: auditLoading,
    },
  ];

  const quickLinks = [
    { label: t("dashboard.manageUsers"), tab: "users", icon: Users },
    { label: t("dashboard.manageRoles"), tab: "roles", icon: ShieldCheck },
    { label: t("dashboard.viewAuditLog"), tab: "audit", icon: ScrollText },
    { label: t("dashboard.configureSso"), tab: "sso", icon: KeyRound },
    { label: t("dashboard.directoryIntegrations"), tab: "directory", icon: FolderSync },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">{t("dashboard.title")}</h2>
        <p className="text-sm text-muted-foreground mt-1">{t("dashboard.description")}</p>
      </div>

      {hasError && !isLoading && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-4">
            <AlertTriangle className="h-5 w-5 text-destructive" />
            <span className="text-sm text-destructive">{t("dashboard.loadError")}</span>
          </CardContent>
        </Card>
      )}

      {/* Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {stats.map((stat) => (
          <Card key={stat.title}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {stat.title}
              </CardTitle>
              <stat.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              {stat.loading ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                <p className="text-3xl font-bold">{stat.value.toLocaleString()}</p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Quick Links */}
      <div>
        <h3 className="text-lg font-semibold mb-3">{t("dashboard.quickLinks")}</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {quickLinks.map((link) => (
            <Button
              key={link.tab}
              variant="outline"
              className="justify-start gap-3 h-auto py-3"
              onClick={() => onTabChange(link.tab)}
            >
              <link.icon className="h-4 w-4 text-primary" />
              <span>{link.label}</span>
            </Button>
          ))}
        </div>
      </div>
    </div>
  );
}
