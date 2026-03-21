// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ShieldCheck, AlertTriangle } from "lucide-react";
import { adminApi } from "@/services/api/admin";
import RoleDetailDialog from "./RoleDetailDialog";

export default function RolesPanel() {
  const { t } = useTranslation("admin");
  const queryClient = useQueryClient();
  const [selectedRole, setSelectedRole] = useState<{ id: number; name: string } | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "roles-full"],
    queryFn: () => adminApi.listRoles(true),
  });

  if (error) {
    return (
      <Card className="border-destructive/50">
        <CardContent className="flex items-center gap-3 py-6">
          <AlertTriangle className="h-5 w-5 text-destructive" />
          <span className="text-sm text-destructive">{t("roles.loadError")}</span>
          <Button variant="outline" size="sm" onClick={() => queryClient.invalidateQueries({ queryKey: ["admin", "roles-full"] })}>
            {t("common.retry")}
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-semibold">{t("roles.title")}</h2>
        <p className="text-sm text-muted-foreground mt-1">{t("roles.description")}</p>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}>
              <CardHeader>
                <Skeleton className="h-5 w-32" />
                <Skeleton className="h-4 w-48" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-4 w-24" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : data?.roles?.length === 0 ? (
        <p className="text-muted-foreground text-center py-8">{t("roles.noRoles")}</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {data?.roles?.map((role) => (
            <Card
              key={role.id}
              className="cursor-pointer hover:border-primary/40 transition-colors"
              onClick={() => setSelectedRole({ id: role.id, name: role.name })}
            >
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-primary" />
                    {role.name}
                  </CardTitle>
                  <div className="flex gap-1">
                    {role.tier && (
                      <Badge variant="outline" className="text-xs">
                        {role.tier}
                      </Badge>
                    )}
                    <Badge variant={role.is_builtin ? "secondary" : "outline"} className="text-xs">
                      {role.is_builtin ? t("roles.builtin") : t("roles.custom")}
                    </Badge>
                  </div>
                </div>
                <CardDescription className="text-xs">{role.description}</CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <p className="text-sm text-muted-foreground">
                  {role.permission_count} {t("roles.permissions")}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {selectedRole && (
        <RoleDetailDialog
          roleId={selectedRole.id}
          roleName={selectedRole.name}
          open={!!selectedRole}
          onOpenChange={(open) => { if (!open) setSelectedRole(null); }}
        />
      )}
    </div>
  );
}
