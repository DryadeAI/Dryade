// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useRef } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import {
  usePreferences,
  defaultPreferences,
  type Theme,
  type DefaultView,
  type AutosaveInterval,
} from "@/hooks/usePreferences";
import {
  Settings,
  Sun,
  Moon,
  Monitor,
  Download,
  Upload,
  RotateCcw,
  Check,
  AlertCircle,
  Sparkles,
  Clock,
  Layout,
  Save,
  Copy,
  Loader2,
} from "lucide-react";

const themeOptions: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];

const viewOptions: { value: DefaultView; label: string }[] = [
  { value: "chat", label: "Chat" },
  { value: "dashboard", label: "Dashboard" },
  { value: "workflows", label: "Workflows" },
];

const autosaveOptions: { value: AutosaveInterval; label: string }[] = [
  { value: "1s", label: "1 second" },
  { value: "5s", label: "5 seconds" },
  { value: "manual", label: "Manual only" },
];

interface PreferencesPanelProps {
  trigger?: React.ReactNode;
}

const PreferencesPanel = ({ trigger }: PreferencesPanelProps) => {
  const {
    preferences,
    updatePreference,
    resetToDefaults,
    exportSettings,
    importSettings,
    resolvedTheme,
  } = usePreferences();

  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const [importError, setImportError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [resetConfirm, setResetConfirm] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">("idle");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Show save feedback when preferences change
  const handlePreferenceChange = <K extends keyof typeof preferences>(
    key: K,
    value: typeof preferences[K]
  ) => {
    setSaveStatus("saving");
    updatePreference(key, value);
    setTimeout(() => {
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 1500);
    }, 300);
  };

  const handleExport = async () => {
    const json = exportSettings();
    try {
      await navigator.clipboard.writeText(json);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback: download as file
      const blob = new Blob([json], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "dryade-preferences.json";
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  const handleImport = () => {
    setImportError(null);
    const success = importSettings(importText);
    if (success) {
      setImportDialogOpen(false);
      setImportText("");
    } else {
      setImportError("Invalid JSON format. Please check your settings file.");
    }
  };

  const handleFileImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (event) => {
        const text = event.target?.result as string;
        setImportText(text);
      };
      reader.readAsText(file);
    }
  };

  const handleReset = () => {
    if (resetConfirm) {
      resetToDefaults();
      setResetConfirm(false);
    } else {
      setResetConfirm(true);
      setTimeout(() => setResetConfirm(false), 3000);
    }
  };

  const hasChanges =
    JSON.stringify(preferences) !== JSON.stringify(defaultPreferences);

  return (
    <Dialog>
      <DialogTrigger asChild>
        {trigger || (
          <Button variant="ghost" size="icon">
            <Settings size={18} />
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-2">
              <Settings size={18} className="text-primary" />
              Preferences
            </span>
            {saveStatus !== "idle" && (
              <span className={cn(
                "text-xs px-2 py-1 rounded-full flex items-center gap-1 transition-opacity",
                saveStatus === "saving" && "bg-muted text-muted-foreground",
                saveStatus === "saved" && "bg-success/10 text-success"
              )}>
                {saveStatus === "saving" ? (
                  <>
                    <Loader2 size={12} className="animate-spin" />
                    Saving...
                  </>
                ) : (
                  <>
                    <Check size={12} />
                    Saved
                  </>
                )}
              </span>
            )}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Theme Section */}
          <div className="space-y-3">
            <Label className="text-sm font-medium flex items-center gap-2">
              <Sun size={14} />
              Theme
            </Label>
            <div className="flex gap-2">
              {themeOptions.map((option) => (
                <Button
                  key={option.value}
                  variant={preferences.theme === option.value ? "default" : "outline"}
                  size="sm"
                  className="flex-1 gap-2"
                  onClick={() => handlePreferenceChange("theme", option.value)}
                >
                  <option.icon size={14} />
                  {option.label}
                </Button>
              ))}
            </div>
            {/* Theme Preview */}
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>Current:</span>
              <span
                className={cn(
                  "px-2 py-0.5 rounded-full capitalize",
                  resolvedTheme === "dark"
                    ? "bg-secondary text-foreground"
                    : "bg-muted text-muted-foreground"
                )}
              >
                {resolvedTheme}
              </span>
            </div>
          </div>

          {/* Toggles Section */}
          <div className="space-y-4">
            {/* Auto-expand reasoning */}
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label
                  htmlFor="auto-expand"
                  className="text-sm font-medium flex items-center gap-2"
                >
                  <Sparkles size={14} />
                  Auto-expand reasoning
                </Label>
                <p className="text-xs text-muted-foreground">
                  Automatically expand AI thinking sections
                </p>
              </div>
              <Switch
                id="auto-expand"
                checked={preferences.autoExpandReasoning}
                onCheckedChange={(checked) =>
                  handlePreferenceChange("autoExpandReasoning", checked)
                }
              />
            </div>

            {/* Show timestamps */}
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label
                  htmlFor="timestamps"
                  className="text-sm font-medium flex items-center gap-2"
                >
                  <Clock size={14} />
                  Show timestamps
                </Label>
                <p className="text-xs text-muted-foreground">
                  Display message timestamps in chat
                </p>
              </div>
              <Switch
                id="timestamps"
                checked={preferences.showTimestamps}
                onCheckedChange={(checked) =>
                  handlePreferenceChange("showTimestamps", checked)
                }
              />
            </div>
          </div>

          {/* Selects Section */}
          <div className="grid gap-4">
            {/* Default View */}
            <div className="space-y-2">
              <Label className="text-sm font-medium flex items-center gap-2">
                <Layout size={14} />
                Default view
              </Label>
              <Select
                value={preferences.defaultView}
                onValueChange={(value: DefaultView) =>
                  handlePreferenceChange("defaultView", value)
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {viewOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Autosave Interval */}
            <div className="space-y-2">
              <Label className="text-sm font-medium flex items-center gap-2">
                <Save size={14} />
                Autosave interval
              </Label>
              <Select
                value={preferences.autosaveInterval}
                onValueChange={(value: AutosaveInterval) =>
                  handlePreferenceChange("autosaveInterval", value)
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {autosaveOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Import/Export Section */}
          <div className="border-t border-border pt-4 space-y-3">
            <Label className="text-sm font-medium text-muted-foreground">
              Settings Data
            </Label>
            <div className="flex gap-2">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    className="flex-1 gap-2"
                    onClick={handleExport}
                  >
                    {copied ? <Check size={14} /> : <Copy size={14} />}
                    {copied ? "Copied!" : "Export"}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Copy settings to clipboard</TooltipContent>
              </Tooltip>

              <Dialog open={importDialogOpen} onOpenChange={setImportDialogOpen}>
                <DialogTrigger asChild>
                  <Button variant="outline" size="sm" className="flex-1 gap-2">
                    <Upload size={14} />
                    Import
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Import Settings</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-4 py-4">
                    <div className="space-y-2">
                      <Label>Paste settings JSON</Label>
                      <Textarea
                        value={importText}
                        onChange={(e) => setImportText(e.target.value)}
                        placeholder='{"theme": "dark", ...}'
                        className="font-mono text-xs h-32"
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">or</span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => fileInputRef.current?.click()}
                      >
                        <Download size={14} />
                        Load from file
                      </Button>
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".json"
                        className="hidden"
                        onChange={handleFileImport}
                      />
                    </div>
                    {importError && (
                      <div className="flex items-center gap-2 text-xs text-destructive bg-destructive/10 p-2 rounded">
                        <AlertCircle size={14} />
                        {importError}
                      </div>
                    )}
                    <Button
                      onClick={handleImport}
                      disabled={!importText.trim()}
                      className="w-full"
                    >
                      Import Settings
                    </Button>
                  </div>
                </DialogContent>
              </Dialog>
            </div>
          </div>

          {/* Reset Section - with clear confirmation */}
          <div className="border-t border-border pt-4">
            {resetConfirm ? (
              <div className="space-y-2 p-3 rounded-lg bg-destructive/10 border border-destructive/30">
                <p className="text-sm text-destructive font-medium">Reset all settings?</p>
                <p className="text-xs text-muted-foreground">
                  This will restore all preferences to their default values. This cannot be undone.
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="flex-1"
                    onClick={() => setResetConfirm(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    className="flex-1 gap-2"
                    onClick={() => {
                      resetToDefaults();
                      setResetConfirm(false);
                    }}
                  >
                    <RotateCcw size={14} />
                    Reset
                  </Button>
                </div>
              </div>
            ) : (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full gap-2"
                  onClick={() => setResetConfirm(true)}
                  disabled={!hasChanges}
                >
                  <RotateCcw size={14} />
                  Reset to defaults
                </Button>
                {!hasChanges && (
                  <p className="text-xs text-muted-foreground text-center mt-2">
                    Using default settings
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default PreferencesPanel;
