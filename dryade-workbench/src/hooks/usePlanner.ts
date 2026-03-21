// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useCallback } from "react";
import { plansApi } from "@/services/api";
import type { PlanCardData } from "@/types/extended-api";

interface UsePlannerResult {
  // State
  prompt: string;
  setPrompt: (prompt: string) => void;
  generatedPlan: PlanCardData | null;
  isGenerating: boolean;
  error: string | null;
  clarification: { questions: string[]; context?: string } | null;

  // Actions
  generate: (conversationId?: string) => Promise<void>;
  setClarification: (c: { questions: string[]; context?: string } | null) => void;
  save: () => Promise<number | null>;  // Returns saved workflow ID
  clear: () => void;
}

export function usePlanner(): UsePlannerResult {
  const [prompt, setPrompt] = useState("");
  const [generatedPlan, setGeneratedPlan] = useState<PlanCardData | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [clarification, setClarification] = useState<{ questions: string[]; context?: string } | null>(null);

  const generate = useCallback(async (conversationId?: string) => {
    if (!prompt.trim()) return;
    setIsGenerating(true);
    setError(null);
    setClarification(null);

    try {
      // Call POST /api/plans/generate with { prompt, conversation_id }
      const response = await plansApi.generatePlan(prompt, conversationId);

      // GAP-P5: Handle clarification response as question UI, not error
      if (response.type === 'clarification') {
        setClarification({
          questions: response.questions || ['Please provide more details'],
          context: response.context || undefined,
        });
        return;
      }
      
      // Access nested plan data
      const plan = response.plan;
      if (!plan) {
        setError('No plan generated');
        return;
      }
      
      setGeneratedPlan({
        id: plan.id,
        name: plan.name,
        description: plan.description || null,
        confidence: plan.confidence || 0.8,
        nodes: plan.nodes?.map(n => ({
          id: n.id,
          agent: n.agent || n.label,
          task: n.description || n.label,
          position: undefined,
        })) || [],
        edges: (plan.edges || []).map(e => ({
          from: e.source || '',
          to: e.target || '',
        })),
        status: plan.status || 'draft',
        ai_generated: true,
        created_at: plan.created_at || new Date().toISOString(),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate plan");
    } finally {
      setIsGenerating(false);
    }
  }, [prompt]);

  const save = useCallback(async () => {
    if (!generatedPlan) return null;

    try {
      // If plan already has ID (was saved by backend during generate), just return it
      if (generatedPlan.id) {
        return generatedPlan.id;
      }

      // Otherwise create new plan
      // Backend expects nodes/edges as top-level fields, not nested in plan_json
      const saved = await plansApi.createPlan({
        name: generatedPlan.name,
        description: generatedPlan.description || "",
        conversation_id: crypto.randomUUID(),
        nodes: generatedPlan.nodes.map(n => ({
          id: n.id,
          agent: n.agent,
          task: n.task,
          depends_on: generatedPlan.edges
            .filter(e => e.to === n.id)
            .map(e => e.from),
        })),
        edges: generatedPlan.edges.map((e, i) => ({
          id: `edge-${i}`,
          from: e.from,
          to: e.to,
        })),
        confidence: generatedPlan.confidence,
        ai_generated: true,
      });

      // Update local state with saved ID
      setGeneratedPlan(prev => prev ? { ...prev, id: saved.id } : null);

      return saved.id;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save plan");
      return null;
    }
  }, [generatedPlan]);

  const clear = useCallback(() => {
    setGeneratedPlan(null);
    setPrompt("");
    setError(null);
    setClarification(null);
  }, []);

  return {
    prompt,
    setPrompt,
    generatedPlan,
    isGenerating,
    error,
    clarification,
    setClarification,
    generate,
    save,
    clear,
  };
}
