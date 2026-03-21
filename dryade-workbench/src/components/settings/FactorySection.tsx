// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// FactorySection - Factory autonomy settings with preset selection
// Renders in Settings > WORKSPACE > Factory
// Persists to localStorage (primary) with best-effort backend sync

import { useEffect, useRef, useCallback } from "react";
import { SettingsCard, SettingRow } from "./SettingsCard";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { useLocalStorage } from "@/hooks/useLocalStorage";
import { cn } from "@/lib/utils";
import { factoryApi } from "@/services/api";

// ---------------------------------------------------------------------------
// Autonomy presets
// ---------------------------------------------------------------------------

const AUTONOMY_PRESETS = {
  conservative: {
    label: "Conservative",
    description: "Manual approval for all creations, no proactive suggestions",
    config: {
      proactive_detection_enabled: false,
      default_test_iterations: 3,
      proactive_max_suggestions_per_day: 0,
    },
  },
  standard: {
    label: "Standard",
    description: "Proactive suggestions enabled, moderate limits",
    config: {
      proactive_detection_enabled: true,
      default_test_iterations: 3,
      proactive_max_suggestions_per_day: 3,
      proactive_max_suggestions_per_session: 1,
    },
  },
  power_user: {
    label: "Power User",
    description: "Aggressive detection, higher suggestion limits",
    config: {
      proactive_detection_enabled: true,
      default_test_iterations: 5,
      proactive_max_suggestions_per_day: 10,
      proactive_max_suggestions_per_session: 3,
    },
  },
} as const;

type PresetKey = keyof typeof AUTONOMY_PRESETS;

const ARTIFACT_TYPES = [
  { key: "agent", label: "Agents" },
  { key: "tool", label: "Tools" },
  { key: "skill", label: "Skills" },
] as const;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const FactorySection = () => {
  const [preset, setPreset] = useLocalStorage<string>(
    "factory-autonomy-preset",
    "standard"
  );
  const [typeOverrides, setTypeOverrides] = useLocalStorage<
    Record<string, boolean>
  >("factory-type-overrides", {});
  const [testIterations, setTestIterations] = useLocalStorage<number>(
    "factory-default-test-iterations",
    AUTONOMY_PRESETS[preset as PresetKey]?.config.default_test_iterations ?? 3
  );

  // Track whether we've loaded from backend to avoid overwriting localStorage on mount
  const backendLoaded = useRef(false);

  // Debounce timer for auto-save
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Build the current settings object
  const buildSettings = useCallback(() => ({
    preset,
    type_overrides: typeOverrides,
    test_iterations: testIterations,
  }), [preset, typeOverrides, testIterations]);

  // Load settings from backend on mount (best-effort)
  useEffect(() => {
    let cancelled = false;
    const loadFromBackend = async () => {
      const remote = await factoryApi.getSettings();
      if (cancelled) return;
      backendLoaded.current = true;
      if (!remote) return;

      // Only apply backend values if they exist
      if (typeof remote.preset === "string" && remote.preset in AUTONOMY_PRESETS) {
        setPreset(remote.preset);
      }
      if (remote.type_overrides && typeof remote.type_overrides === "object") {
        setTypeOverrides(remote.type_overrides as Record<string, boolean>);
      }
      if (typeof remote.test_iterations === "number") {
        setTestIterations(remote.test_iterations);
      }
    };
    loadFromBackend();
    return () => { cancelled = true; };
    // Only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Debounced auto-save to backend when settings change
  useEffect(() => {
    // Skip the initial render / backend load
    if (!backendLoaded.current) return;

    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      factoryApi.saveSettings(buildSettings());
    }, 1500);

    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, [buildSettings]);

  const handlePresetChange = (value: string) => {
    setPreset(value);
    const presetConfig =
      AUTONOMY_PRESETS[value as PresetKey]?.config;
    if (presetConfig) {
      setTestIterations(presetConfig.default_test_iterations);
    }
  };

  const toggleTypeOverride = (type: string) => {
    setTypeOverrides((prev) => ({
      ...prev,
      [type]: prev[type] === undefined ? false : !prev[type],
    }));
  };

  return (
    <div className="space-y-4">
      {/* Autonomy Level */}
      <SettingsCard
        title="Autonomy Level"
        description="Control how aggressively the factory detects and suggests artifact creation"
      >
        <RadioGroup
          value={preset}
          onValueChange={handlePresetChange}
          className="space-y-1 py-1"
        >
          {(Object.entries(AUTONOMY_PRESETS) as [PresetKey, (typeof AUTONOMY_PRESETS)[PresetKey]][]).map(
            ([key, p]) => (
              <label
                key={key}
                htmlFor={`preset-${key}`}
                className={cn(
                  "flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors",
                  preset === key
                    ? "border-primary/50 bg-primary/5"
                    : "border-transparent hover:bg-muted/50"
                )}
              >
                <RadioGroupItem value={key} id={`preset-${key}`} className="mt-0.5" />
                <div className="space-y-0.5">
                  <p className="text-sm font-medium text-foreground">
                    {p.label}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {p.description}
                  </p>
                </div>
              </label>
            )
          )}
        </RadioGroup>
      </SettingsCard>

      {/* Artifact Type Overrides */}
      <SettingsCard
        title="Artifact Type Detection"
        description="Enable or disable proactive detection per artifact type"
      >
        {ARTIFACT_TYPES.map(({ key, label }) => (
          <SettingRow
            key={key}
            label={label}
            description={`Detect opportunities to create ${label.toLowerCase()}`}
          >
            <Switch
              checked={typeOverrides[key] !== false}
              onCheckedChange={() => toggleTypeOverride(key)}
            />
          </SettingRow>
        ))}
      </SettingsCard>

      {/* Test Configuration */}
      <SettingsCard
        title="Test Configuration"
        description="Default settings for artifact validation"
      >
        <SettingRow
          label="Max test iterations"
          description={`Run up to ${testIterations} test-fix cycles during creation`}
        >
          <div className="flex items-center gap-3 w-48">
            <Slider
              value={[testIterations]}
              onValueChange={([v]) => setTestIterations(v)}
              min={1}
              max={10}
              step={1}
            />
            <span className="text-sm font-medium text-foreground w-6 text-right">
              {testIterations}
            </span>
          </div>
        </SettingRow>
      </SettingsCard>
    </div>
  );
};
