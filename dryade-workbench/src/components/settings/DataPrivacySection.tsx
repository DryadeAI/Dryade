// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Download, AlertTriangle } from "lucide-react";
import { SettingsCard, SettingRow } from "./SettingsCard";
import { toast } from "sonner";
import type { AppSettings } from "@/types/extended-api";

interface DataPrivacySectionProps {
  settings: AppSettings;
  onSettingsChange: (settings: AppSettings) => void;
}

export const DataPrivacySection = ({ settings, onSettingsChange }: DataPrivacySectionProps) => {
  const updateData = (patch: Partial<AppSettings["data"]>) =>
    onSettingsChange({ ...settings, data: { ...settings.data, ...patch } });

  const handleExportData = () => {
    const data = JSON.stringify(settings, null, 2);
    const blob = new Blob([data], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "dryade-settings.json";
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Settings exported");
  };

  const handleClearLocalStorage = () => {
    localStorage.clear();
    toast.success("Local storage cleared");
  };

  return (
    <div className="space-y-4">
      <SettingsCard title="Auto-save" description="Control how your work is saved">
        <SettingRow label="Auto-save" description="Automatically save changes">
          <Switch checked={settings.data.auto_save} onCheckedChange={(checked) => updateData({ auto_save: checked })} />
        </SettingRow>
        {settings.data.auto_save && (
          <div className="py-2">
            <div className="flex items-center justify-between mb-2">
              <Label className="text-sm">Save Interval</Label>
              <span className="text-xs text-muted-foreground">{settings.data.save_interval_seconds}s</span>
            </div>
            <Slider
              value={[settings.data.save_interval_seconds]}
              onValueChange={([value]) => updateData({ save_interval_seconds: value })}
              min={10} max={120} step={10}
            />
          </div>
        )}
      </SettingsCard>

      <SettingsCard title="Storage">
        <div className="flex flex-wrap gap-2 py-2">
          <Button variant="outline" size="sm" onClick={handleExportData}>
            <Download className="w-4 h-4 mr-2" />Export Settings
          </Button>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="outline" size="sm">Clear Local Storage</Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Clear Local Storage?</AlertDialogTitle>
                <AlertDialogDescription>This will clear all locally stored preferences and cache.</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={handleClearLocalStorage}>Clear</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </SettingsCard>

      <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-5">
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-destructive mt-0.5" />
          <div className="space-y-2">
            <h4 className="font-medium text-destructive">Danger Zone</h4>
            <p className="text-sm text-muted-foreground">Once you delete your account, there is no going back.</p>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" size="sm">Delete Account</Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete Account?</AlertDialogTitle>
                  <AlertDialogDescription>This will permanently delete your account and all associated data.</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90">Delete Account</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>
      </div>
    </div>
  );
};
