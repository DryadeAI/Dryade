// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { Switch } from "@/components/ui/switch";
import { SettingsCard, SettingRow } from "./SettingsCard";
import type { AppSettings } from "@/types/extended-api";

interface NotificationsSectionProps {
  settings: AppSettings;
  onSettingsChange: (settings: AppSettings) => void;
}

export const NotificationsSection = ({ settings, onSettingsChange }: NotificationsSectionProps) => {
  const updateNotif = (patch: Partial<AppSettings["notifications"]>) =>
    onSettingsChange({ ...settings, notifications: { ...settings.notifications, ...patch } });

  return (
    <div className="space-y-4">
      <SettingsCard title="Email" description="Control which emails you receive">
        <SettingRow label="Email Notifications" description="Receive notifications via email">
          <Switch
            checked={settings.notifications.email_enabled}
            onCheckedChange={(checked) => updateNotif({ email_enabled: checked })}
          />
        </SettingRow>
        {settings.notifications.email_enabled && (
          <>
            {[
              { key: "workflow_complete", label: "Workflow Completions" },
              { key: "plan_approval", label: "Plan Approval Requests" },
              { key: "system_alerts", label: "System Alerts" },
              { key: "weekly_digest", label: "Weekly Digest" },
            ].map((category) => (
              <SettingRow key={category.key} label={category.label} className="pl-4">
                <Switch
                  checked={settings.notifications.email_categories[category.key as keyof typeof settings.notifications.email_categories]}
                  onCheckedChange={(checked) => updateNotif({
                    email_categories: { ...settings.notifications.email_categories, [category.key]: checked }
                  })}
                />
              </SettingRow>
            ))}
          </>
        )}
      </SettingsCard>

      <SettingsCard title="Alerts">
        <SettingRow label="Sound Effects" description="Play sounds for important events">
          <Switch checked={settings.notifications.sound_enabled} onCheckedChange={(checked) => updateNotif({ sound_enabled: checked })} />
        </SettingRow>
        <SettingRow label="Desktop Notifications" description="Show browser notifications">
          <Switch checked={settings.notifications.desktop_enabled} onCheckedChange={(checked) => updateNotif({ desktop_enabled: checked })} />
        </SettingRow>
      </SettingsCard>
    </div>
  );
};
