// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Sun, Moon, Monitor } from "lucide-react";
import { cn } from "@/lib/utils";
import { SettingsCard, SettingRow } from "./SettingsCard";
import type { AppSettings } from "@/types/extended-api";

interface AppearanceSectionProps {
  settings: AppSettings;
  onSettingsChange: (settings: AppSettings) => void;
}

export const AppearanceSection = ({ settings, onSettingsChange }: AppearanceSectionProps) => {
  const update = (patch: Partial<AppSettings["appearance"]>) =>
    onSettingsChange({ ...settings, appearance: { ...settings.appearance, ...patch } });

  return (
    <div className="space-y-4">
      <SettingsCard title="Theme" description="Choose your preferred color scheme">
        <div className="py-2">
          <RadioGroup
            value={settings.appearance.theme}
            onValueChange={(value) => update({ theme: value as "light" | "dark" | "system" })}
            className="grid grid-cols-3 gap-3"
          >
            {[
              { value: "light", label: "Light", icon: Sun },
              { value: "dark", label: "Dark", icon: Moon },
              { value: "system", label: "System", icon: Monitor },
            ].map((option) => (
              <Label key={option.value} className={cn(
                "flex flex-col items-center gap-2 p-4 rounded-lg border cursor-pointer transition-all",
                settings.appearance.theme === option.value
                  ? "border-primary bg-primary/5 shadow-sm"
                  : "border-border hover:border-primary/50"
              )}>
                <RadioGroupItem value={option.value} className="sr-only" />
                <option.icon className="w-5 h-5" />
                <span className="text-sm">{option.label}</span>
              </Label>
            ))}
          </RadioGroup>
        </div>
      </SettingsCard>

      <SettingsCard title="Display">
        <SettingRow label="Font Size" description="Adjust the base font size">
          <Select value={settings.appearance.font_size} onValueChange={(value) => update({ font_size: value as "small" | "medium" | "large" })}>
            <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="small">Small</SelectItem>
              <SelectItem value="medium">Medium</SelectItem>
              <SelectItem value="large">Large</SelectItem>
            </SelectContent>
          </Select>
        </SettingRow>
        <SettingRow label="Compact Mode" description="Reduce spacing and padding">
          <Switch checked={settings.appearance.compact_mode} onCheckedChange={(checked) => update({ compact_mode: checked })} />
        </SettingRow>
        <SettingRow label="Collapse Sidebar by Default" description="Start with sidebar minimized">
          <Switch checked={settings.appearance.sidebar_collapsed} onCheckedChange={(checked) => update({ sidebar_collapsed: checked })} />
        </SettingRow>
      </SettingsCard>
    </div>
  );
};
