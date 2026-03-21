// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// PropertiesPanel - Node/edge configuration panel
// Based on COMPONENTS-4.md specification

import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { X, Plus, Trash2, Settings2, ShieldCheck } from "lucide-react";
import type { Node, Edge } from "@xyflow/react";

interface PropertiesPanelProps {
  selectedNode?: Node;
  selectedEdge?: Edge;
  onNodeUpdate: (nodeId: string, data: Record<string, unknown>) => void;
  onEdgeUpdate: (edgeId: string, data: Record<string, unknown>) => void;
  availableAgents?: string[];
  availableTools?: string[];
  onClose?: () => void;
  className?: string;
  workflowId?: number;
  onClearPendingApproval?: (nodeId: string) => void;
}

interface ConditionEntry {
  id: string;
  expression: string;
  target: string;
}

const PropertiesPanel = ({
  selectedNode,
  selectedEdge,
  onNodeUpdate,
  onEdgeUpdate,
  availableAgents = [],
  availableTools = [],
  onClose,
  className,
  workflowId,
  onClearPendingApproval,
}: PropertiesPanelProps) => {
  const [localData, setLocalData] = useState<Record<string, unknown>>({});
  const [conditions, setConditions] = useState<ConditionEntry[]>([]);
  // Approval runtime state
  const [approvalNote, setApprovalNote] = useState("");
  const [editMode, setEditMode] = useState(false);
  const [modifiedFields, setModifiedFields] = useState<Record<string, unknown>>({});
  const [approvalSubmitting, setApprovalSubmitting] = useState(false);

  // Sync with selected node/edge
  useEffect(() => {
    // Reset approval state on node change
    setApprovalNote("");
    setEditMode(false);
    setModifiedFields({});
    setApprovalSubmitting(false);

    if (selectedNode) {
      setLocalData(selectedNode.data as Record<string, unknown>);
      if (selectedNode.type === "router" && (selectedNode.data as Record<string, unknown>).conditions) {
        setConditions((selectedNode.data as Record<string, unknown>).conditions as ConditionEntry[] || []);
      } else {
        setConditions([]);
      }
    } else if (selectedEdge) {
      setLocalData(selectedEdge.data as Record<string, unknown> || {});
      setConditions([]);
    } else {
      setLocalData({});
      setConditions([]);
    }
  }, [selectedNode, selectedEdge]);

  const handleUpdate = (key: string, value: unknown) => {
    const newData = { ...localData, [key]: value };
    setLocalData(newData);
    
    if (selectedNode) {
      onNodeUpdate(selectedNode.id, newData);
    } else if (selectedEdge) {
      onEdgeUpdate(selectedEdge.id, newData);
    }
  };

  const handleConditionAdd = () => {
    const newCondition: ConditionEntry = {
      id: `cond-${Date.now()}`,
      expression: "",
      target: "",
    };
    const newConditions = [...conditions, newCondition];
    setConditions(newConditions);
    handleUpdate("conditions", newConditions);
  };

  const handleConditionRemove = (id: string) => {
    const newConditions = conditions.filter((c) => c.id !== id);
    setConditions(newConditions);
    handleUpdate("conditions", newConditions);
  };

  const handleConditionChange = (id: string, field: keyof ConditionEntry, value: string) => {
    const newConditions = conditions.map((c) =>
      c.id === id ? { ...c, [field]: value } : c
    );
    setConditions(newConditions);
    handleUpdate("conditions", newConditions);
  };

  const submitApproval = async (action: "approve" | "reject" | "modify") => {
    if (!workflowId || !selectedNode) return;
    const requestId = localData.approval_request_id as number | undefined;
    if (!requestId) return;

    setApprovalSubmitting(true);
    try {
      const body: Record<string, unknown> = { action, note: approvalNote || undefined };
      if (action === "modify") {
        body.modified_fields = modifiedFields;
      }
      const res = await fetch(
        `/api/workflows/${workflowId}/approvals/${requestId}/action`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify(body),
        }
      );
      if (!res.ok) {
        console.error("[APPROVAL] Action failed:", await res.text());
        return;
      }
      // Reset state and notify canvas to clear awaiting_approval indicator
      setEditMode(false);
      setModifiedFields({});
      setApprovalNote("");
      if (onClearPendingApproval) {
        onClearPendingApproval(selectedNode.id);
      }
    } catch (e) {
      console.error("[APPROVAL] submitApproval error:", e);
    } finally {
      setApprovalSubmitting(false);
    }
  };

  if (!selectedNode && !selectedEdge) {
    return (
      <Card className={cn("h-full flex items-center justify-center", className)}>
        <CardContent className="text-center py-12">
          <Settings2 className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
          <p className="text-muted-foreground">
            Select a node or edge to view properties
          </p>
        </CardContent>
      </Card>
    );
  }

  const nodeType = selectedNode?.type || "edge";

  return (
    <Card className={cn("h-full overflow-hidden flex flex-col", className)}>
      <CardHeader className="pb-3 flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle className="text-lg">Properties</CardTitle>
            <Badge variant="outline" className="capitalize">
              {nodeType}
            </Badge>
          </div>
          {onClose && (
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="w-4 h-4" />
            </Button>
          )}
        </div>
      </CardHeader>

      <CardContent className="flex-1 overflow-y-auto space-y-4">
        {/* Common: Label */}
        <div className="space-y-2">
          <Label htmlFor="label">Label</Label>
          <Input
            id="label"
            value={String(localData.label || "")}
            onChange={(e) => handleUpdate("label", e.target.value)}
            placeholder="Enter label..."
          />
        </div>

        <Separator />

        {/* TaskNode specific fields */}
        {nodeType === "task" && (
          <>
            <div className="space-y-2">
              <Label htmlFor="agent">Agent</Label>
              <Select
                value={String(localData.agent || "")}
                onValueChange={(value) => handleUpdate("agent", value)}
              >
                <SelectTrigger id="agent">
                  <SelectValue placeholder="Select agent..." />
                </SelectTrigger>
                <SelectContent>
                  {availableAgents.map((agent) => (
                    <SelectItem key={agent} value={agent}>
                      {agent}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="taskDescription">Task Description</Label>
              <Textarea
                id="taskDescription"
                value={String(localData.taskDescription || "")}
                onChange={(e) => handleUpdate("taskDescription", e.target.value)}
                placeholder="Describe the task..."
                rows={3}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="expectedOutput">Expected Output</Label>
              <Textarea
                id="expectedOutput"
                value={String(localData.expectedOutput || "")}
                onChange={(e) => handleUpdate("expectedOutput", e.target.value)}
                placeholder="Expected output format..."
                rows={2}
              />
            </div>
          </>
        )}

        {/* RouterNode specific fields */}
        {nodeType === "router" && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label>Conditions</Label>
              <Button variant="outline" size="sm" onClick={handleConditionAdd}>
                <Plus className="w-3 h-3 mr-1" />
                Add
              </Button>
            </div>

            {conditions.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                No conditions defined. Add conditions to control routing.
              </p>
            ) : (
              <div className="space-y-2">
                {conditions.map((condition, idx) => (
                  <div
                    key={condition.id}
                    className="p-3 rounded-lg bg-muted/30 space-y-2"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-muted-foreground">
                        Condition {idx + 1}
                      </span>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6"
                        onClick={() => handleConditionRemove(condition.id)}
                      >
                        <Trash2 className="w-3 h-3 text-destructive" />
                      </Button>
                    </div>
                    <Input
                      value={condition.expression}
                      onChange={(e) =>
                        handleConditionChange(condition.id, "expression", e.target.value)
                      }
                      placeholder="Expression (e.g., result == 'yes')"
                      className="text-sm"
                    />
                    <Input
                      value={condition.target}
                      onChange={(e) =>
                        handleConditionChange(condition.id, "target", e.target.value)
                      }
                      placeholder="Target node ID"
                      className="text-sm"
                    />
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ToolNode specific fields */}
        {nodeType === "tool" && (
          <>
            <div className="space-y-2">
              <Label htmlFor="tool">Tool</Label>
              <Select
                value={String(localData.tool || "")}
                onValueChange={(value) => handleUpdate("tool", value)}
              >
                <SelectTrigger id="tool">
                  <SelectValue placeholder="Select tool..." />
                </SelectTrigger>
                <SelectContent>
                  {availableTools.map((tool) => (
                    <SelectItem key={tool} value={tool}>
                      {tool}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="arguments">Arguments (JSON)</Label>
              <Textarea
                id="arguments"
                value={
                  typeof localData.arguments === "object"
                    ? JSON.stringify(localData.arguments, null, 2)
                    : String(localData.arguments || "{}")
                }
                onChange={(e) => {
                  try {
                    handleUpdate("arguments", JSON.parse(e.target.value));
                  } catch {
                    // Allow invalid JSON while typing
                  }
                }}
                placeholder='{"key": "value"}'
                rows={4}
                className="font-mono text-sm"
              />
            </div>
          </>
        )}

        {/* ApprovalNode: Runtime action panel (shown when awaiting approval) */}
        {nodeType === "approval" && (localData.runtime_status === "awaiting_approval" || localData.status === "awaiting_approval") && (
          <div className="border border-amber-500/40 rounded-lg p-3 bg-amber-950/20 space-y-3">
            <div className="flex items-center gap-2">
              <ShieldCheck size={16} className="text-amber-400" />
              <h3 className="text-sm font-semibold text-amber-200">Approval Required</h3>
            </div>

            {/* Prompt */}
            {localData.prompt && (
              <p className="text-xs text-amber-300/80 italic">{String(localData.prompt)}</p>
            )}

            {/* Display fields with current values */}
            {Array.isArray(localData.display_fields) && (localData.display_fields as string[]).length > 0 && (
              <div className="space-y-1.5">
                <p className="text-xs font-medium text-amber-200/70">Workflow State</p>
                {(localData.display_fields as string[]).map((field) => (
                  <div key={field} className="flex items-start gap-2">
                    <span className="text-xs text-amber-300/60 w-28 shrink-0 mt-0.5">{field}:</span>
                    {editMode ? (
                      <Input
                        className="flex-1 text-xs h-6 px-2"
                        value={String(modifiedFields[field] ?? (localData.state_values as Record<string, unknown>)?.[field] ?? "")}
                        onChange={(e) => setModifiedFields((prev) => ({ ...prev, [field]: e.target.value }))}
                      />
                    ) : (
                      <span className="text-xs text-amber-100">
                        {String((localData.state_values as Record<string, unknown>)?.[field] ?? "N/A")}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Optional note */}
            <Textarea
              className="text-xs"
              placeholder="Optional note..."
              value={approvalNote}
              onChange={(e) => setApprovalNote(e.target.value)}
              rows={2}
            />

            {/* Action buttons */}
            <div className="flex gap-1.5 flex-wrap">
              <button
                disabled={approvalSubmitting}
                onClick={() => submitApproval("approve")}
                className="flex-1 text-xs px-2 py-1.5 rounded bg-green-700 hover:bg-green-600 text-white font-medium disabled:opacity-50"
              >
                Approve
              </button>
              <button
                disabled={approvalSubmitting}
                onClick={() => setEditMode(!editMode)}
                className="flex-1 text-xs px-2 py-1.5 rounded bg-blue-700 hover:bg-blue-600 text-white font-medium disabled:opacity-50"
              >
                {editMode ? "Cancel" : "Modify"}
              </button>
              {editMode && (
                <button
                  disabled={approvalSubmitting}
                  onClick={() => submitApproval("modify")}
                  className="flex-1 text-xs px-2 py-1.5 rounded bg-blue-900 hover:bg-blue-800 text-white font-medium disabled:opacity-50"
                >
                  Save &amp; Approve
                </button>
              )}
              <button
                disabled={approvalSubmitting}
                onClick={() => submitApproval("reject")}
                className="flex-1 text-xs px-2 py-1.5 rounded bg-red-700 hover:bg-red-600 text-white font-medium disabled:opacity-50"
              >
                Reject
              </button>
            </div>
          </div>
        )}

        {/* ApprovalNode: Design-time config form */}
        {nodeType === "approval" && localData.runtime_status !== "awaiting_approval" && localData.status !== "awaiting_approval" && (
          <>
            <Separator />
            <div className="flex items-center gap-2">
              <ShieldCheck size={14} className="text-amber-400" />
              <Label className="text-amber-300">Approval Configuration</Label>
            </div>

            <div className="space-y-2">
              <Label htmlFor="approvalPrompt">Approval Prompt <span className="text-red-400">*</span></Label>
              <Textarea
                id="approvalPrompt"
                value={String(localData.prompt || "")}
                onChange={(e) => handleUpdate("prompt", e.target.value)}
                placeholder="Describe what the approver should check..."
                rows={3}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="approver">Who Can Approve</Label>
              <Select
                value={String(localData.approver || "owner")}
                onValueChange={(v) => handleUpdate("approver", v)}
              >
                <SelectTrigger id="approver">
                  <SelectValue placeholder="Select approver type..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="owner">Workflow Owner Only</SelectItem>
                  <SelectItem value="specific_user">Specific User</SelectItem>
                  <SelectItem value="any_member">Any Team Member</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {localData.approver === "specific_user" && (
              <div className="space-y-2">
                <Label htmlFor="approverUserId">Approver User ID</Label>
                <Input
                  id="approverUserId"
                  value={String(localData.approver_user_id || "")}
                  onChange={(e) => handleUpdate("approver_user_id", e.target.value)}
                  placeholder="user_id or email..."
                />
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="displayFields">Display Fields (comma-separated)</Label>
              <Input
                id="displayFields"
                value={
                  Array.isArray(localData.display_fields)
                    ? (localData.display_fields as string[]).join(", ")
                    : String(localData.display_fields || "")
                }
                onChange={(e) => handleUpdate("display_fields", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
                placeholder="e.g. report_summary, user_name"
              />
              <p className="text-xs text-muted-foreground">State fields visible to the approver</p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="timeoutHours">Timeout (hours)</Label>
              <Input
                id="timeoutHours"
                type="number"
                min={1}
                value={Math.round((Number(localData.timeout_seconds) || 86400) / 3600)}
                onChange={(e) => handleUpdate("timeout_seconds", Number(e.target.value) * 3600)}
                placeholder="24"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="timeoutAction">On Timeout</Label>
              <Select
                value={String(localData.timeout_action || "reject")}
                onValueChange={(v) => handleUpdate("timeout_action", v)}
              >
                <SelectTrigger id="timeoutAction">
                  <SelectValue placeholder="Select timeout action..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="reject">Auto-Reject</SelectItem>
                  <SelectItem value="approve">Auto-Approve</SelectItem>
                  <SelectItem value="escalate">Escalate</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </>
        )}

        {/* Edge specific fields */}
        {selectedEdge && (
          <>
            <div className="space-y-2">
              <Label>Source</Label>
              <Input value={selectedEdge.source} disabled className="bg-muted" />
            </div>
            <div className="space-y-2">
              <Label>Target</Label>
              <Input value={selectedEdge.target} disabled className="bg-muted" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="condition">Condition (optional)</Label>
              <Input
                id="condition"
                value={String(localData.condition || "")}
                onChange={(e) => handleUpdate("condition", e.target.value)}
                placeholder="Condition expression..."
              />
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
};

export default PropertiesPanel;
