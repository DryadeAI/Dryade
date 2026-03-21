// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";
import { Card, CardContent } from "@/components/ui/card";
import { ChevronLeft, ChevronRight, AlertTriangle, UserPlus, UserMinus } from "lucide-react";
import { toast } from "sonner";
import { adminApi } from "@/services/api/admin";
import type { AdminUser } from "@/types/admin";
import AssignRoleDialog from "./AssignRoleDialog";

export default function UsersPanel() {
  const { t } = useTranslation("admin");
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [roleFilter, setRoleFilter] = useState<string>("all");
  const [assignUser, setAssignUser] = useState<AdminUser | null>(null);
  const perPage = 25;

  const { data: rolesData } = useQuery({
    queryKey: ["admin", "roles"],
    queryFn: () => adminApi.listRoles(true),
  });

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "users", page, roleFilter],
    queryFn: () =>
      adminApi.listUsers({
        page,
        per_page: perPage,
        role: roleFilter !== "all" ? roleFilter : undefined,
      }),
  });

  const removeMutation = useMutation({
    mutationFn: ({ userId, roleId }: { userId: string; roleId: number }) =>
      adminApi.removeRole(userId, roleId),
    onSuccess: () => {
      toast.success(t("users.removeRole"));
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
    onError: () => {
      toast.error(t("common.error"));
    },
  });

  const totalPages = data ? Math.ceil(data.total / perPage) : 0;

  const formatLastSeen = (date?: string) => {
    if (!date) return t("users.never");
    const d = new Date(date);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    if (diffDays === 0) return "Today";
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 30) return `${diffDays}d ago`;
    return d.toLocaleDateString();
  };

  if (error) {
    return (
      <Card className="border-destructive/50">
        <CardContent className="flex items-center gap-3 py-6">
          <AlertTriangle className="h-5 w-5 text-destructive" />
          <span className="text-sm text-destructive">{t("common.error")}</span>
          <Button variant="outline" size="sm" onClick={() => queryClient.invalidateQueries({ queryKey: ["admin", "users"] })}>
            {t("common.retry")}
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-semibold">{t("users.title")}</h2>
        <p className="text-sm text-muted-foreground mt-1">{t("users.description")}</p>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-3">
        <Select value={roleFilter} onValueChange={(v) => { setRoleFilter(v); setPage(1); }}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder={t("users.filterByRole")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("users.allRoles")}</SelectItem>
            {rolesData?.roles?.map((role) => (
              <SelectItem key={role.id} value={role.name}>{role.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <div className="border rounded-md">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("users.email")}</TableHead>
              <TableHead>{t("users.displayName")}</TableHead>
              <TableHead>{t("users.role")}</TableHead>
              <TableHead>{t("users.status")}</TableHead>
              <TableHead>{t("users.lastSeen")}</TableHead>
              <TableHead className="text-right">{t("users.actions")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 6 }).map((_, j) => (
                    <TableCell key={j}><Skeleton className="h-4 w-24" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : data?.users?.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                  {t("users.noUsers")}
                </TableCell>
              </TableRow>
            ) : (
              data?.users?.map((user) => (
                <TableRow key={user.user_id}>
                  <TableCell className="font-medium">{user.email}</TableCell>
                  <TableCell>{user.display_name || "-"}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{user.global_role || "user"}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={user.is_active ? "default" : "secondary"}>
                      {user.is_active ? t("users.active") : t("users.inactive")}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {formatLastSeen(user.last_seen)}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setAssignUser(user)}
                        title={t("users.assignRole")}
                      >
                        <UserPlus className="h-4 w-4" />
                      </Button>
                      {user.global_role !== "admin" && (
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button variant="ghost" size="sm" title={t("users.removeRole")}>
                              <UserMinus className="h-4 w-4" />
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>{t("users.removeRole")}</AlertDialogTitle>
                              <AlertDialogDescription>
                                {t("users.confirmRemoveRole", { role: user.global_role || "user" })}
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
                              <AlertDialogAction
                                onClick={() => removeMutation.mutate({ userId: user.user_id, roleId: 0 })}
                              >
                                {t("common.confirm")}
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            {t("users.pageOf", { page, pages: totalPages })}
          </p>
          <div className="flex gap-1">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
            >
              <ChevronLeft className="h-4 w-4" />
              {t("users.previous")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
            >
              {t("users.next")}
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Assign Role Dialog */}
      {assignUser && (
        <AssignRoleDialog
          user={assignUser}
          open={!!assignUser}
          onOpenChange={(open) => { if (!open) setAssignUser(null); }}
        />
      )}
    </div>
  );
}
