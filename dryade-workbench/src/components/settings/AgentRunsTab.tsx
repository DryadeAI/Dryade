// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * Settings tab for agent run preferences.
 * Controls tool call display, capability auto-accept, and other agent execution settings.
 */
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { usePreferences, type ToolCallDisplay } from "@/hooks/usePreferences";

export function AgentRunsTab() {
  const { preferences, updateAgentRunPreference } = usePreferences();
  const { agentRuns } = preferences;

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-medium">Agent Execution</h3>
        <p className="text-sm text-muted-foreground">
          Configure how agent runs are displayed in the chat interface.
        </p>
      </div>

      {/* Tool Call Display */}
      <div className="space-y-3">
        <Label htmlFor="tool-display">Tool Call Display</Label>
        <Select
          value={agentRuns.toolCallDisplay}
          onValueChange={(value: ToolCallDisplay) =>
            updateAgentRunPreference("toolCallDisplay", value)
          }
        >
          <SelectTrigger id="tool-display" className="w-[200px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="collapsed">Always Collapsed</SelectItem>
            <SelectItem value="expanded">Always Expanded</SelectItem>
            <SelectItem value="smart-collapse">Smart Collapse</SelectItem>
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          Smart collapse expands short outputs and collapses long ones.
        </p>
      </div>

      {/* Smart Collapse Threshold */}
      {agentRuns.toolCallDisplay === "smart-collapse" && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <Label>Collapse Threshold</Label>
            <span className="text-sm text-muted-foreground">
              {agentRuns.smartCollapseThreshold} lines
            </span>
          </div>
          <Slider
            value={[agentRuns.smartCollapseThreshold]}
            onValueChange={([value]) =>
              updateAgentRunPreference("smartCollapseThreshold", value)
            }
            min={5}
            max={50}
            step={5}
            className="w-full"
          />
          <p className="text-xs text-muted-foreground">
            Tool outputs longer than this will be collapsed by default.
          </p>
        </div>
      )}

      {/* Show Timestamps */}
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <Label htmlFor="show-timestamps">Show Timestamps</Label>
          <p className="text-xs text-muted-foreground">
            Display execution time for each tool call.
          </p>
        </div>
        <Switch
          id="show-timestamps"
          checked={agentRuns.showTimestamps}
          onCheckedChange={(checked) =>
            updateAgentRunPreference("showTimestamps", checked)
          }
        />
      </div>

      {/* Show Raw Output */}
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <Label htmlFor="show-raw">Show Raw Output</Label>
          <p className="text-xs text-muted-foreground">
            Display unformatted tool output instead of formatted view.
          </p>
        </div>
        <Switch
          id="show-raw"
          checked={agentRuns.showRawOutput}
          onCheckedChange={(checked) =>
            updateAgentRunPreference("showRawOutput", checked)
          }
        />
      </div>

      <div className="border-t pt-6">
        <h3 className="text-lg font-medium">Capability Permissions</h3>
        <p className="text-sm text-muted-foreground">
          Control how agents request and receive new capabilities.
        </p>
      </div>

      {/* Auto Accept Capabilities */}
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <Label htmlFor="auto-accept">Auto-Accept Capabilities</Label>
          <p className="text-xs text-muted-foreground">
            Automatically approve capability requests without prompting.
          </p>
        </div>
        <Switch
          id="auto-accept"
          checked={agentRuns.autoAcceptCapabilities}
          onCheckedChange={(checked) =>
            updateAgentRunPreference("autoAcceptCapabilities", checked)
          }
        />
      </div>

      {/* Accept All Session (ephemeral) */}
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <Label htmlFor="accept-all-session">Accept All This Session</Label>
          <p className="text-xs text-muted-foreground">
            Auto-approve for this session only. Resets on page refresh.
          </p>
        </div>
        <Switch
          id="accept-all-session"
          checked={agentRuns.acceptAllSession}
          onCheckedChange={(checked) =>
            updateAgentRunPreference("acceptAllSession", checked)
          }
        />
      </div>
    </div>
  );
}
