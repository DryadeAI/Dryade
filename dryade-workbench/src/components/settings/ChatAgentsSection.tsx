// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { Switch } from "@/components/ui/switch";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { SettingsCard, SettingRow } from "./SettingsCard";
import { AgentRunsTab } from "./AgentRunsTab";
import type { AppSettings } from "@/types/extended-api";

interface ChatAgentsSectionProps {
  settings: AppSettings;
  onSettingsChange: (settings: AppSettings) => void;
}

export const ChatAgentsSection = ({ settings, onSettingsChange }: ChatAgentsSectionProps) => {
  const updateChat = (patch: Partial<AppSettings["chat"]>) =>
    onSettingsChange({ ...settings, chat: { ...settings.chat, ...patch } });

  return (
    <div className="space-y-4">
      <SettingsCard title="Chat" description="Configure the chat interface">
        <SettingRow label="Default Mode" description="Starting mode for new conversations">
          <Select value={settings.chat.default_mode} onValueChange={(value) => updateChat({ default_mode: value })}>
            <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="chat">Chat</SelectItem>
              <SelectItem value="agent">Agent</SelectItem>
              <SelectItem value="code">Code</SelectItem>
            </SelectContent>
          </Select>
        </SettingRow>
        <SettingRow label="Syntax Theme" description="Code block color scheme">
          <Select value={settings.chat.syntax_theme} onValueChange={(value) => updateChat({ syntax_theme: value as AppSettings["chat"]["syntax_theme"] })}>
            <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="github">GitHub</SelectItem>
              <SelectItem value="dracula">Dracula</SelectItem>
              <SelectItem value="monokai">Monokai</SelectItem>
              <SelectItem value="vs-code">VS Code</SelectItem>
            </SelectContent>
          </Select>
        </SettingRow>
        <SettingRow label="Auto-scroll" description="Scroll to new messages automatically">
          <Switch checked={settings.chat.auto_scroll} onCheckedChange={(checked) => updateChat({ auto_scroll: checked })} />
        </SettingRow>
        <SettingRow label="Show Timestamps" description="Display time for each message">
          <Switch checked={settings.chat.show_timestamps} onCheckedChange={(checked) => updateChat({ show_timestamps: checked })} />
        </SettingRow>
        <SettingRow label="Expand Reasoning by Default" description="Show AI reasoning automatically">
          <Switch checked={settings.chat.expand_reasoning} onCheckedChange={(checked) => updateChat({ expand_reasoning: checked })} />
        </SettingRow>
      </SettingsCard>

      <SettingsCard title="Agent Execution" description="Configure how agent runs are displayed">
        <div className="py-2">
          <AgentRunsTab />
        </div>
      </SettingsCard>
    </div>
  );
};
