// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { KeyRound, Globe, AlertTriangle, Truck } from "lucide-react";
import { adminApi } from "@/services/api/admin";

export default function SsoPanel() {
  const { t } = useTranslation("admin");

  const { data: ssoStatus, isLoading: ssoLoading, error: ssoError } = useQuery({
    queryKey: ["admin", "sso-status"],
    queryFn: () => adminApi.getSsoStatus(),
    retry: false,
  });

  const { data: providersData, isLoading: providersLoading } = useQuery({
    queryKey: ["admin", "sso-providers"],
    queryFn: () => adminApi.getSsoProviders(),
    enabled: !!ssoStatus?.configured,
    retry: false,
  });

  const { data: shipperStatus, isLoading: shipperLoading } = useQuery({
    queryKey: ["admin", "shipper-status"],
    queryFn: () => adminApi.getShipperStatus(),
    retry: false,
  });

  const ssoUnavailable = ssoError && (ssoError as Error & { status?: number })?.status === 503;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">{t("sso.title")}</h2>
        <p className="text-sm text-muted-foreground mt-1">{t("sso.description")}</p>
      </div>

      {/* SSO Status Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <KeyRound className="h-5 w-5 text-primary" />
              <CardTitle className="text-base">SSO</CardTitle>
            </div>
            {ssoLoading ? (
              <Skeleton className="h-5 w-20" />
            ) : ssoUnavailable ? (
              <Badge variant="secondary">{t("sso.ssoUnavailable")}</Badge>
            ) : ssoStatus?.enabled ? (
              <Badge variant="default">{t("sso.enabled")}</Badge>
            ) : (
              <Badge variant="secondary">{t("sso.disabled")}</Badge>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {ssoLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-4 w-32" />
            </div>
          ) : ssoUnavailable ? (
            <p className="text-sm text-muted-foreground">{t("sso.ssoUnavailable")}</p>
          ) : ssoStatus?.configured ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Badge variant="outline">{t("sso.configured")}</Badge>
              </div>
              {ssoStatus.issuer && (
                <p className="text-sm text-muted-foreground">
                  {t("sso.issuer")}: <span className="font-mono text-xs">{ssoStatus.issuer}</span>
                </p>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              <Badge variant="outline">{t("sso.notConfigured")}</Badge>
              <div className="bg-muted/50 rounded-md p-4 space-y-2">
                <p className="text-sm font-medium">{t("sso.setupGuide")}</p>
                <div className="font-mono text-xs space-y-1 text-muted-foreground">
                  <p>DRYADE_ZITADEL_ENABLED=true</p>
                  <p>DRYADE_ZITADEL_ISSUER=&lt;your-zitadel-url&gt;</p>
                  <p>DRYADE_ZITADEL_PROJECT_ID=&lt;your-project-id&gt;</p>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Providers List */}
      {ssoStatus?.configured && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Globe className="h-4 w-4" />
              {t("sso.providers")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {providersLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : providersData?.providers?.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("sso.noProviders")}</p>
            ) : (
              <div className="space-y-2">
                {providersData?.providers?.map((provider) => (
                  <div
                    key={provider.id}
                    className="flex items-center justify-between p-3 border rounded-md"
                  >
                    <div className="flex items-center gap-3">
                      <Globe className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm font-medium">{provider.name}</span>
                    </div>
                    <Badge variant={provider.enabled ? "default" : "secondary"}>
                      {provider.enabled ? t("sso.providerEnabled") : t("sso.providerDisabled")}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Audit Log Shipper Status */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Truck className="h-4 w-4 text-primary" />
              <CardTitle className="text-base">{t("sso.shipperStatus")}</CardTitle>
            </div>
            {shipperLoading ? (
              <Skeleton className="h-5 w-20" />
            ) : shipperStatus ? (
              <Badge variant={shipperStatus.status === "active" ? "default" : "secondary"}>
                {shipperStatus.status === "active" ? t("sso.shipperActive") : t("sso.shipperStopped")}
              </Badge>
            ) : (
              <Badge variant="secondary">{t("sso.shipperUnavailable")}</Badge>
            )}
          </div>
        </CardHeader>
        {shipperStatus && (
          <CardContent className="space-y-2">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-muted-foreground">Version</p>
                <p className="font-medium">{shipperStatus.version}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Tier</p>
                <p className="font-medium">{shipperStatus.tier}</p>
              </div>
            </div>
            {shipperStatus.sinks && Object.keys(shipperStatus.sinks).length > 0 && (
              <div>
                <p className="text-sm text-muted-foreground">Sinks</p>
                <div className="flex gap-2 mt-1">
                  {Object.keys(shipperStatus.sinks).map((sink) => (
                    <Badge key={sink} variant="outline">{sink}</Badge>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        )}
      </Card>
    </div>
  );
}
