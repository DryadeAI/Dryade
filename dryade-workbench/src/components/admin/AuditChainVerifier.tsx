// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Loader2, ShieldCheck } from "lucide-react";
import { adminApi } from "@/services/api/admin";
import type { AuditChainStatus } from "@/types/admin";

export default function AuditChainVerifier() {
  const { t } = useTranslation("admin");
  const [verifying, setVerifying] = useState(false);
  const [result, setResult] = useState<AuditChainStatus | null>(null);

  const handleVerify = async () => {
    setVerifying(true);
    try {
      const status = await adminApi.verifyAuditChain();
      setResult(status);
    } catch {
      setResult(null);
    } finally {
      setVerifying(false);
    }
  };

  const statusVariant = (status: string): "default" | "destructive" | "secondary" => {
    switch (status) {
      case "intact": return "default";
      case "broken": return "destructive";
      case "partial": return "secondary";
      default: return "secondary";
    }
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-primary" />
            <CardTitle className="text-sm">{t("chainVerifier.title")}</CardTitle>
            <Badge variant="outline" className="text-[10px]">{t("chainVerifier.soc2")}</Badge>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleVerify}
            disabled={verifying}
          >
            {verifying ? (
              <>
                <Loader2 className="h-3 w-3 animate-spin mr-1" />
                {t("chainVerifier.verifying")}
              </>
            ) : (
              t("chainVerifier.verify")
            )}
          </Button>
        </div>
        <CardDescription className="text-xs">{t("chainVerifier.description")}</CardDescription>
      </CardHeader>
      {result && (
        <CardContent className="pt-0">
          <div className="flex items-center gap-4 text-sm">
            <Badge variant={statusVariant(result.status)}>
              {t(`chainVerifier.${result.status}`)}
            </Badge>
            <span className="text-muted-foreground">
              {t("chainVerifier.verified")}: {result.verified}
            </span>
            <span className="text-muted-foreground">
              {t("chainVerifier.brokenCount")}: {result.broken}
            </span>
          </div>
          {result.message && (
            <p className="text-xs text-muted-foreground mt-1">{result.message}</p>
          )}
        </CardContent>
      )}
    </Card>
  );
}
