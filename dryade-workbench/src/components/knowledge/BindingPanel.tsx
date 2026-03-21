// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { 
  Link2, 
  Bot, 
  Users, 
  X,
  Check,
  Loader2
} from "lucide-react";
import { toast } from "sonner";

interface Agent {
  id: string;
  name: string;
  description?: string;
  framework: string;
}

interface Crew {
  id: string;
  name: string;
  description?: string;
  agent_count: number;
}

interface BindingPanelProps {
  sourceId: string;
  sourceName: string;
  availableAgents: Agent[];
  availableCrews: Crew[];
  boundAgents: string[];
  boundCrews: string[];
  onSave: (agents: string[], crews: string[]) => Promise<void>;
  onClose: () => void;
  className?: string;
}

const BindingPanel = ({
  sourceId,
  sourceName,
  availableAgents,
  availableCrews,
  boundAgents,
  boundCrews,
  onSave,
  onClose,
  className,
}: BindingPanelProps) => {
  const [selectedAgents, setSelectedAgents] = useState<string[]>(boundAgents);
  const [selectedCrews, setSelectedCrews] = useState<string[]>(boundCrews);
  const [saving, setSaving] = useState(false);

  const toggleAgent = (agentId: string) => {
    setSelectedAgents((prev) =>
      prev.includes(agentId)
        ? prev.filter((id) => id !== agentId)
        : [...prev, agentId]
    );
  };

  const toggleCrew = (crewId: string) => {
    setSelectedCrews((prev) =>
      prev.includes(crewId)
        ? prev.filter((id) => id !== crewId)
        : [...prev, crewId]
    );
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(selectedAgents, selectedCrews);
      toast.success("Bindings updated successfully");
      onClose();
    } catch (error) {
      toast.error("Failed to update bindings");
    } finally {
      setSaving(false);
    }
  };

  const hasChanges =
    JSON.stringify(selectedAgents.sort()) !== JSON.stringify(boundAgents.sort()) ||
    JSON.stringify(selectedCrews.sort()) !== JSON.stringify(boundCrews.sort());

  return (
    <Card className={cn("w-80", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Link2 className="w-5 h-5 text-primary" />
            <CardTitle className="text-base">Bind Source</CardTitle>
          </div>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onClose}>
            <X className="w-4 h-4" />
          </Button>
        </div>
        <p className="text-sm text-muted-foreground mt-1">
          Link "{sourceName}" to agents or crews
        </p>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Agents Section */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Bot className="w-4 h-4 text-muted-foreground" />
            <span className="text-sm font-medium">Agents</span>
            {selectedAgents.length > 0 && (
              <Badge variant="secondary" className="ml-auto">
                {selectedAgents.length}
              </Badge>
            )}
          </div>
          <ScrollArea className="h-32 rounded-md border p-2">
            {availableAgents.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                No agents available
              </p>
            ) : (
              <div className="space-y-2">
                {availableAgents.map((agent) => (
                  <label
                    key={agent.id}
                    className={cn(
                      "flex items-center gap-2 p-2 rounded-lg cursor-pointer transition-colors",
                      selectedAgents.includes(agent.id)
                        ? "bg-primary/10"
                        : "hover:bg-muted"
                    )}
                  >
                    <Checkbox
                      checked={selectedAgents.includes(agent.id)}
                      onCheckedChange={() => toggleAgent(agent.id)}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{agent.name}</p>
                      <p className="text-xs text-muted-foreground truncate">
                        {agent.framework}
                      </p>
                    </div>
                  </label>
                ))}
              </div>
            )}
          </ScrollArea>
        </div>

        <Separator />

        {/* Crews Section */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Users className="w-4 h-4 text-muted-foreground" />
            <span className="text-sm font-medium">Crews</span>
            {selectedCrews.length > 0 && (
              <Badge variant="secondary" className="ml-auto">
                {selectedCrews.length}
              </Badge>
            )}
          </div>
          <ScrollArea className="h-32 rounded-md border p-2">
            {availableCrews.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                No crews available
              </p>
            ) : (
              <div className="space-y-2">
                {availableCrews.map((crew) => (
                  <label
                    key={crew.id}
                    className={cn(
                      "flex items-center gap-2 p-2 rounded-lg cursor-pointer transition-colors",
                      selectedCrews.includes(crew.id)
                        ? "bg-primary/10"
                        : "hover:bg-muted"
                    )}
                  >
                    <Checkbox
                      checked={selectedCrews.includes(crew.id)}
                      onCheckedChange={() => toggleCrew(crew.id)}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{crew.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {crew.agent_count} agents
                      </p>
                    </div>
                  </label>
                ))}
              </div>
            )}
          </ScrollArea>
        </div>

        {/* Actions */}
        <div className="flex gap-2 pt-2">
          <Button
            variant="outline"
            className="flex-1"
            onClick={onClose}
            disabled={saving}
          >
            Cancel
          </Button>
          <Button
            className="flex-1"
            onClick={handleSave}
            disabled={!hasChanges || saving}
          >
            {saving ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <>
                <Check className="w-4 h-4 mr-1" />
                Save
              </>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
};

export default BindingPanel;
