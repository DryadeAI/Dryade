// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useTranslation } from "react-i18next";
import { FolderSync, Globe } from "lucide-react";
import LdapConfigCard from "./LdapConfigCard";
import ScimStatusCard from "./ScimStatusCard";

export default function DirectoryPanel() {
  const { t } = useTranslation("admin");

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">{t("directory.title")}</h2>
        <p className="text-sm text-muted-foreground mt-1">{t("directory.description")}</p>
      </div>

      {/* LDAP Section */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <FolderSync className="h-5 w-5 text-primary" />
          <h3 className="text-lg font-semibold">{t("directory.ldapTitle")}</h3>
        </div>
        <LdapConfigCard />
      </div>

      {/* SCIM Section */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Globe className="h-5 w-5 text-primary" />
          <h3 className="text-lg font-semibold">{t("directory.scimTitle")}</h3>
        </div>
        <ScimStatusCard />
      </div>
    </div>
  );
}
