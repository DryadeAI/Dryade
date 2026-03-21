// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { adminApi } from "@/services/api/admin";
import type { AdminUser } from "@/types/admin";

interface AssignRoleDialogProps {
  user: AdminUser;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function AssignRoleDialog({ user, open, onOpenChange }: AssignRoleDialogProps) {
  const { t } = useTranslation("admin");
  const queryClient = useQueryClient();
  const [selectedRoleId, setSelectedRoleId] = useState<string>("");
  const [scopeType, setScopeType] = useState<string>("global");

  const { data: rolesData } = useQuery({
    queryKey: ["admin", "roles"],
    queryFn: () => adminApi.listRoles(true),
    enabled: open,
  });

  const assignMutation = useMutation({
    mutationFn: () =>
      adminApi.assignRole(user.user_id, {
        role_id: parseInt(selectedRoleId, 10),
        scope_type: scopeType !== "global" ? scopeType : undefined,
      }),
    onSuccess: () => {
      toast.success(t("assignRoleDialog.success"));
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      onOpenChange(false);
      setSelectedRoleId("");
    },
    onError: () => {
      toast.error(t("assignRoleDialog.error"));
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("assignRoleDialog.title")}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div>
            <p className="text-sm text-muted-foreground">{user.email}</p>
            <p className="text-xs text-muted-foreground">
              {t("assignRoleDialog.currentRole")}: {user.global_role || "user"}
            </p>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">{t("assignRoleDialog.selectRole")}</label>
            <Select value={selectedRoleId} onValueChange={setSelectedRoleId}>
              <SelectTrigger>
                <SelectValue placeholder={t("assignRoleDialog.selectRole")} />
              </SelectTrigger>
              <SelectContent>
                {rolesData?.roles?.map((role) => (
                  <SelectItem key={role.id} value={String(role.id)}>
                    {role.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">{t("assignRoleDialog.scopeType")}</label>
            <Select value={scopeType} onValueChange={setScopeType}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="global">{t("assignRoleDialog.global")}</SelectItem>
                <SelectItem value="project">{t("assignRoleDialog.project")}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              {t("assignRoleDialog.cancel")}
            </Button>
            <Button
              onClick={() => assignMutation.mutate()}
              disabled={!selectedRoleId || assignMutation.isPending}
            >
              {t("assignRoleDialog.assign")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
