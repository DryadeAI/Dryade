// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Check, X } from "lucide-react";
import { adminApi } from "@/services/api/admin";

interface RoleDetailDialogProps {
  roleId: number;
  roleName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function RoleDetailDialog({ roleId, roleName, open, onOpenChange }: RoleDetailDialogProps) {
  const { t } = useTranslation("admin");

  const { data, isLoading } = useQuery({
    queryKey: ["admin", "role-permissions", roleId],
    queryFn: () => adminApi.getRolePermissions(roleId),
    enabled: open,
  });

  // Group permissions by scope prefix
  const groupedPermissions = data?.permissions?.reduce<Record<string, typeof data.permissions>>((acc, perm) => {
    const group = perm.scope.split(".")[0] || "other";
    if (!acc[group]) acc[group] = [];
    acc[group].push(perm);
    return acc;
  }, {}) ?? {};

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[80vh] overflow-auto">
        <DialogHeader>
          <DialogTitle>
            {t("roleDetail.title")}: {roleName}
          </DialogTitle>
          {data?.inherited_from && (
            <p className="text-sm text-muted-foreground">
              {t("roleDetail.inheritedFrom", { role: data.inherited_from })}
            </p>
          )}
        </DialogHeader>

        {isLoading ? (
          <div className="space-y-2 py-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : Object.keys(groupedPermissions).length === 0 ? (
          <p className="text-muted-foreground py-8 text-center text-sm">
            {t("roleDetail.noPermissions")}
          </p>
        ) : (
          <div className="space-y-4">
            {Object.entries(groupedPermissions).map(([group, perms]) => (
              <div key={group}>
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                  {group}.*
                </h4>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("roleDetail.scope")}</TableHead>
                      <TableHead>{t("roleDetail.action")}</TableHead>
                      <TableHead className="w-20 text-center">{t("roleDetail.granted")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {perms.map((perm, i) => (
                      <TableRow key={i}>
                        <TableCell className="font-mono text-xs">{perm.scope}</TableCell>
                        <TableCell>{perm.action}</TableCell>
                        <TableCell className="text-center">
                          {perm.granted ? (
                            <Check className="h-4 w-4 text-green-500 mx-auto" />
                          ) : (
                            <X className="h-4 w-4 text-red-500 mx-auto" />
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ))}
          </div>
        )}

        <div className="flex justify-end pt-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("roleDetail.close")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
