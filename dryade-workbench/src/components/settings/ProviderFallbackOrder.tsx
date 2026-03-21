// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// ProviderFallbackOrder — drag-and-drop provider fallback ordering.
// Rendered inside ApiKeysSection.tsx with no new pages or tabs.

import {
  DndContext,
  closestCenter,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import type { DragEndEvent } from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  verticalListSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import type { HealthStatus } from "@/hooks/useProviderHealth";
import type { FallbackChainEntry } from "@/hooks/useProviderHealth";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ProviderFallbackOrderProps {
  providers: Array<{
    id: string;          // "openai:gpt-4o"
    displayName: string; // "OpenAI (GPT-4o)"
    provider: string;    // "openai"
    model: string;       // "gpt-4o"
    hasKey: boolean;     // whether user has configured API key
  }>;
  healthData: Record<string, { status: HealthStatus }>;
  enabled: boolean;
  onOrderChange: (newChain: FallbackChainEntry[]) => void;
  onEnabledChange: (enabled: boolean) => void;
}

// ---------------------------------------------------------------------------
// Health dot indicator
// ---------------------------------------------------------------------------

function HealthDot({ status }: { status: HealthStatus | undefined }) {
  const colors: Record<HealthStatus, string> = {
    green: "bg-green-500",
    yellow: "bg-yellow-400",
    red: "bg-red-500",
  };
  const color = status ? colors[status] : "bg-gray-300";
  return (
    <span
      className={`inline-block w-2.5 h-2.5 rounded-full ${color} shrink-0`}
      aria-label={`Provider status: ${status ?? "unknown"}`}
    />
  );
}

// ---------------------------------------------------------------------------
// SortableProviderRow
// ---------------------------------------------------------------------------

interface SortableProviderRowProps {
  id: string;
  displayName: string;
  provider: string;
  model: string;
  hasKey: boolean;
  healthStatus: HealthStatus | undefined;
  disabled: boolean;
}

function SortableProviderRow({
  id,
  displayName,
  hasKey,
  healthStatus,
  disabled,
}: SortableProviderRowProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id, disabled });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`flex items-center gap-3 p-3 rounded-lg border border-border bg-card
        ${!hasKey ? "opacity-50" : ""}
        ${disabled ? "cursor-default" : "cursor-grab active:cursor-grabbing"}
      `}
    >
      {/* Drag handle */}
      <span
        {...attributes}
        {...listeners}
        className="text-muted-foreground shrink-0"
        aria-label="Drag to reorder"
      >
        <GripVertical className="w-4 h-4" />
      </span>

      {/* Health dot */}
      <HealthDot status={healthStatus} />

      {/* Provider display name */}
      <span className="flex-1 text-sm font-medium">{displayName}</span>

      {/* No key indicator */}
      {!hasKey && (
        <span className="text-xs text-muted-foreground">(no key)</span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ProviderFallbackOrder
// ---------------------------------------------------------------------------

export function ProviderFallbackOrder({
  providers,
  healthData,
  enabled,
  onOrderChange,
  onEnabledChange,
}: ProviderFallbackOrderProps) {
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor)
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = providers.findIndex((p) => p.id === active.id);
    const newIndex = providers.findIndex((p) => p.id === over.id);
    if (oldIndex === -1 || newIndex === -1) return;

    const reordered = arrayMove(providers, oldIndex, newIndex);
    onOrderChange(
      reordered.map((p) => ({ provider: p.provider, model: p.model }))
    );
  };

  return (
    <div className="space-y-3">
      {/* Header row with toggle */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">Fallback Order</p>
          <p className="text-xs text-muted-foreground">
            Drag to reorder which provider is tried first when the primary fails
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Label htmlFor="fallback-enabled" className="text-sm text-muted-foreground">
            {enabled ? "Enabled" : "Disabled"}
          </Label>
          <Switch
            id="fallback-enabled"
            checked={enabled}
            onCheckedChange={onEnabledChange}
          />
        </div>
      </div>

      {/* Sortable list */}
      {providers.length === 0 ? (
        <p className="text-sm text-muted-foreground py-2">
          No providers configured. Add API keys above to set up a fallback chain.
        </p>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={providers.map((p) => p.id)}
            strategy={verticalListSortingStrategy}
          >
            <div className="space-y-2">
              {providers.map((provider) => (
                <SortableProviderRow
                  key={provider.id}
                  id={provider.id}
                  displayName={provider.displayName}
                  provider={provider.provider}
                  model={provider.model}
                  hasKey={provider.hasKey}
                  healthStatus={healthData[provider.provider]?.status}
                  disabled={!enabled}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}
    </div>
  );
}
