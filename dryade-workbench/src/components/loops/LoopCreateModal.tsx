// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useEffect, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Badge } from "@/components/ui/badge";
import { useCreateLoop } from "@/hooks/useLoops";
import { agentsApi } from "@/services/api/agents";
import { scenariosApi } from "@/services/api/workflows";
import { Loader2, Clock, Calendar, Zap } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

interface LoopCreateModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface TargetOption {
  value: string;
  label: string;
}

const TARGET_TYPES = [
  { value: "workflow", label: "Workflow", icon: "🔄" },
  { value: "agent", label: "Agent", icon: "🤖" },
  { value: "orchestrator_task", label: "Free-form Task", icon: "✨" },
];

const TRIGGER_TYPES = [
  { value: "cron", label: "Cron", icon: Calendar, description: "Precise scheduling" },
  { value: "interval", label: "Interval", icon: Clock, description: "Repeat every X" },
  { value: "oneshot", label: "One-shot", icon: Zap, description: "Run once" },
];

const INTERVAL_PRESETS = [
  { value: "5m", label: "5 min" },
  { value: "15m", label: "15 min" },
  { value: "30m", label: "30 min" },
  { value: "1h", label: "1 hour" },
  { value: "4h", label: "4 hours" },
  { value: "12h", label: "12 hours" },
  { value: "1d", label: "Daily" },
];

const CRON_PRESETS = [
  { value: "0 * * * *", label: "Every hour" },
  { value: "0 */6 * * *", label: "Every 6 hours" },
  { value: "0 9 * * *", label: "Daily at 9 AM" },
  { value: "0 9 * * 1-5", label: "Weekdays at 9 AM" },
  { value: "0 0 * * 0", label: "Weekly (Sun midnight)" },
  { value: "0 0 1 * *", label: "Monthly (1st)" },
];

const TIMEZONES = [
  { value: "UTC", label: "UTC" },
  { value: "Europe/Paris", label: "Europe/Paris (CET)" },
  { value: "Europe/London", label: "Europe/London (GMT)" },
  { value: "Europe/Berlin", label: "Europe/Berlin (CET)" },
  { value: "America/New_York", label: "America/New York (EST)" },
  { value: "America/Chicago", label: "America/Chicago (CST)" },
  { value: "America/Denver", label: "America/Denver (MST)" },
  { value: "America/Los_Angeles", label: "America/Los Angeles (PST)" },
  { value: "America/Sao_Paulo", label: "America/Sao Paulo (BRT)" },
  { value: "Asia/Tokyo", label: "Asia/Tokyo (JST)" },
  { value: "Asia/Shanghai", label: "Asia/Shanghai (CST)" },
  { value: "Asia/Kolkata", label: "Asia/Kolkata (IST)" },
  { value: "Asia/Dubai", label: "Asia/Dubai (GST)" },
  { value: "Asia/Singapore", label: "Asia/Singapore (SGT)" },
  { value: "Australia/Sydney", label: "Australia/Sydney (AEST)" },
  { value: "Pacific/Auckland", label: "Pacific/Auckland (NZST)" },
  { value: "Africa/Cairo", label: "Africa/Cairo (EET)" },
];

export default function LoopCreateModal({ open, onOpenChange }: LoopCreateModalProps) {
  const [name, setName] = useState("");
  const [targetType, setTargetType] = useState("workflow");
  const [targetId, setTargetId] = useState("");
  const [triggerType, setTriggerType] = useState("interval");
  const [schedule, setSchedule] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [targetOptions, setTargetOptions] = useState<TargetOption[]>([]);
  const [loadingTargets, setLoadingTargets] = useState(false);

  const createLoop = useCreateLoop();

  // Fetch available targets when target type changes
  useEffect(() => {
    if (!open) return;
    setTargetId("");
    setTargetOptions([]);

    if (targetType === "orchestrator_task") return;

    setLoadingTargets(true);
    const fetchTargets = async () => {
      try {
        if (targetType === "workflow") {
          const scenarios = await scenariosApi.listScenarios();
          setTargetOptions(
            scenarios.map((s) => ({
              value: s.name,
              label: s.name.replace(/[-_]/g, " "),
            }))
          );
        } else if (targetType === "agent") {
          const { agents } = await agentsApi.getAgents();
          setTargetOptions(
            agents.map((a) => ({
              value: a.name,
              label: a.name,
            }))
          );
        }
      } catch {
        setTargetOptions([]);
      } finally {
        setLoadingTargets(false);
      }
    };
    fetchTargets();
  }, [targetType, open]);

  // Auto-generate name from target selection
  const autoName = useMemo(() => {
    if (name) return name;
    if (!targetId) return "";
    const prefix = targetId.replace(/[-_]/g, "-").toLowerCase();
    const suffix = triggerType === "interval" && schedule ? schedule : triggerType;
    return `${prefix}-${suffix}`;
  }, [targetId, triggerType, schedule, name]);

  const handleSubmit = async () => {
    const finalName = name.trim() || autoName;
    if (!finalName || !schedule.trim()) {
      toast.error("Name and schedule are required.");
      return;
    }
    if (targetType !== "orchestrator_task" && !targetId) {
      toast.error("Please select a target.");
      return;
    }
    if (targetType === "orchestrator_task" && !targetId.trim()) {
      toast.error("Please enter a task description.");
      return;
    }

    try {
      await createLoop.mutateAsync({
        name: finalName,
        target_type: targetType,
        target_id: targetType === "orchestrator_task" ? targetId.trim() : targetId,
        trigger_type: triggerType,
        schedule: schedule.trim(),
        timezone,
      });
      toast.success(`Loop "${finalName}" created.`);
      resetForm();
      onOpenChange(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to create loop.";
      if (typeof msg === "string" && msg.includes("already exists")) {
        toast.error("A loop with this name already exists. Choose a different name.");
      } else {
        toast.error(msg);
      }
    }
  };

  const resetForm = () => {
    setName("");
    setTargetType("workflow");
    setTargetId("");
    setTriggerType("interval");
    setSchedule("");
    setTimezone("UTC");
    setTargetOptions([]);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Create Scheduled Loop</DialogTitle>
          <DialogDescription>
            Schedule a workflow, agent, or task to run automatically.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-1">
          {/* Target Type — visual pills */}
          <div className="space-y-2">
            <Label className="text-xs uppercase tracking-wider text-muted-foreground">What to run</Label>
            <div className="flex gap-2">
              {TARGET_TYPES.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => setTargetType(t.value)}
                  className={cn(
                    "flex-1 flex items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-sm font-medium transition-all",
                    targetType === t.value
                      ? "border-primary/50 bg-primary/10 text-primary shadow-sm"
                      : "border-border/40 bg-background/50 text-muted-foreground hover:border-border hover:bg-muted/30"
                  )}
                >
                  <span>{t.icon}</span>
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          {/* Target Selection */}
          <div className="space-y-2">
            {targetType === "orchestrator_task" ? (
              <>
                <Label htmlFor="loop-target-id" className="text-xs uppercase tracking-wider text-muted-foreground">
                  Task description
                </Label>
                <Input
                  id="loop-target-id"
                  value={targetId}
                  onChange={(e) => setTargetId(e.target.value)}
                  placeholder="Summarize today's events and send digest"
                />
              </>
            ) : (
              <>
                <Label className="text-xs uppercase tracking-wider text-muted-foreground">
                  {targetType === "workflow" ? "Workflow" : "Agent"}
                </Label>
                {loadingTargets ? (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Loading available {targetType === "workflow" ? "workflows" : "agents"}...
                  </div>
                ) : targetOptions.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-2">
                    No {targetType === "workflow" ? "workflows" : "agents"} found.
                  </p>
                ) : (
                  <Select value={targetId} onValueChange={setTargetId}>
                    <SelectTrigger>
                      <SelectValue placeholder={`Select a ${targetType}`} />
                    </SelectTrigger>
                    <SelectContent>
                      {targetOptions.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </>
            )}
          </div>

          {/* Trigger Type — cards */}
          <div className="space-y-2">
            <Label className="text-xs uppercase tracking-wider text-muted-foreground">How often</Label>
            <RadioGroup value={triggerType} onValueChange={(v) => { setTriggerType(v); setSchedule(""); }} className="grid grid-cols-3 gap-2">
              {TRIGGER_TYPES.map((t) => {
                const Icon = t.icon;
                return (
                  <label
                    key={t.value}
                    htmlFor={`trigger-${t.value}`}
                    className={cn(
                      "flex flex-col items-center gap-1 rounded-lg border px-3 py-2.5 cursor-pointer transition-all text-center",
                      triggerType === t.value
                        ? "border-primary/50 bg-primary/10 text-primary shadow-sm"
                        : "border-border/40 bg-background/50 text-muted-foreground hover:border-border hover:bg-muted/30"
                    )}
                  >
                    <RadioGroupItem value={t.value} id={`trigger-${t.value}`} className="sr-only" />
                    <Icon className="h-4 w-4" />
                    <span className="text-sm font-medium">{t.label}</span>
                    <span className="text-[10px] opacity-70">{t.description}</span>
                  </label>
                );
              })}
            </RadioGroup>
          </div>

          {/* Schedule — context-dependent UX */}
          <div className="space-y-2">
            <Label className="text-xs uppercase tracking-wider text-muted-foreground">Schedule</Label>

            {triggerType === "interval" && (
              <div className="flex flex-wrap gap-1.5">
                {INTERVAL_PRESETS.map((p) => (
                  <Badge
                    key={p.value}
                    variant={schedule === p.value ? "default" : "outline"}
                    className={cn(
                      "cursor-pointer transition-all px-3 py-1",
                      schedule === p.value
                        ? "bg-primary text-primary-foreground"
                        : "hover:bg-muted/50"
                    )}
                    onClick={() => setSchedule(p.value)}
                  >
                    {p.label}
                  </Badge>
                ))}
                <Input
                  value={INTERVAL_PRESETS.some(p => p.value === schedule) ? "" : schedule}
                  onChange={(e) => setSchedule(e.target.value)}
                  placeholder="Custom (e.g. 2h, 45m)"
                  className="mt-1.5 h-8 text-sm"
                />
              </div>
            )}

            {triggerType === "cron" && (
              <div className="space-y-2">
                <div className="flex flex-wrap gap-1.5">
                  {CRON_PRESETS.map((p) => (
                    <Badge
                      key={p.value}
                      variant={schedule === p.value ? "default" : "outline"}
                      className={cn(
                        "cursor-pointer transition-all px-2.5 py-1 text-xs",
                        schedule === p.value
                          ? "bg-primary text-primary-foreground"
                          : "hover:bg-muted/50"
                      )}
                      onClick={() => setSchedule(p.value)}
                    >
                      {p.label}
                    </Badge>
                  ))}
                </div>
                <Input
                  value={schedule}
                  onChange={(e) => setSchedule(e.target.value)}
                  placeholder="0 */6 * * * (min hour day month weekday)"
                  className="h-8 text-sm font-mono"
                />
                <p className="text-[11px] text-muted-foreground">
                  Standard 5-field cron: minute hour day-of-month month day-of-week
                </p>
              </div>
            )}

            {triggerType === "oneshot" && (
              <div className="space-y-1.5">
                <Input
                  type="datetime-local"
                  value={schedule}
                  onChange={(e) => setSchedule(e.target.value)}
                  className="h-9 text-sm"
                />
                <p className="text-[11px] text-muted-foreground">
                  Run once at the specified date and time.
                </p>
              </div>
            )}
          </div>

          {/* Timezone */}
          <div className="space-y-2">
            <Label className="text-xs uppercase tracking-wider text-muted-foreground">Timezone</Label>
            <Select value={timezone} onValueChange={setTimezone}>
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TIMEZONES.map((tz) => (
                  <SelectItem key={tz.value} value={tz.value}>
                    {tz.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Name — auto-suggested */}
          <div className="space-y-2">
            <Label htmlFor="loop-name" className="text-xs uppercase tracking-wider text-muted-foreground">
              Loop name
            </Label>
            <Input
              id="loop-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={autoName || "daily-report-generation"}
              className="h-9 text-sm"
            />
            {!name && autoName && (
              <p className="text-[11px] text-muted-foreground">
                Auto-generated: <span className="font-mono">{autoName}</span>
              </p>
            )}
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={createLoop.isPending}>
            {createLoop.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Create Loop
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
