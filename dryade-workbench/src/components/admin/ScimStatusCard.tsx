// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Check, X, Eye, EyeOff } from "lucide-react";
import { adminApi } from "@/services/api/admin";

export default function ScimStatusCard() {
  const { t } = useTranslation("admin");
  const [showToken, setShowToken] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "scim-config"],
    queryFn: () => adminApi.scimGetServiceProviderConfig(),
    retry: false,
  });

  const scimUnavailable = error || !data;
  const baseUrl = window.location.origin;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base">{t("directory.scimTitle")}</CardTitle>
            <CardDescription className="text-xs">{t("directory.scimDescription")}</CardDescription>
          </div>
          {isLoading ? (
            <Skeleton className="h-5 w-24" />
          ) : scimUnavailable ? (
            <Badge variant="secondary">{t("scim.endpointInactive")}</Badge>
          ) : (
            <Badge variant="default">{t("scim.endpointActive")}</Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-4 w-36" />
          </div>
        ) : scimUnavailable ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">{t("scim.pluginUnavailable")}</p>
            <div className="bg-muted/50 rounded-md p-4">
              <p className="text-xs text-muted-foreground">{t("scim.setupGuide")}</p>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Endpoint URL */}
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">{t("scim.endpointUrl")}</p>
              <code className="text-xs bg-muted px-2 py-1 rounded font-mono">
                {baseUrl}/scim/v2/
              </code>
            </div>

            {/* Supported Features */}
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-2">{t("scim.supportedFeatures")}</p>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { key: "patch", supported: data.patch?.supported },
                  { key: "filter", supported: data.filter?.supported },
                  { key: "bulk", supported: data.bulk?.supported },
                  { key: "sort", supported: data.sort?.supported },
                ].map((feature) => (
                  <div key={feature.key} className="flex items-center gap-1.5">
                    {feature.supported ? (
                      <Check className="h-3 w-3 text-green-500" />
                    ) : (
                      <X className="h-3 w-3 text-red-500" />
                    )}
                    <span className="text-xs">{t(`scim.${feature.key}`)}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Setup Instructions */}
            <div className="bg-muted/50 rounded-md p-3">
              <p className="text-xs text-muted-foreground">{t("scim.setupInstructions")}</p>
            </div>

            {/* Bearer Token */}
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">{t("scim.bearerToken")}</p>
              <div className="flex items-center gap-2">
                <code className="text-xs bg-muted px-2 py-1 rounded font-mono flex-1">
                  {showToken ? "Set via DRYADE_SCIM_BEARER_TOKEN env var" : "********"}
                </code>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowToken(!showToken)}
                  className="h-7 px-2"
                >
                  {showToken ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                  <span className="ml-1 text-xs">
                    {showToken ? t("scim.hideToken") : t("scim.showToken")}
                  </span>
                </Button>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
