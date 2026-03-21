// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { InferenceParamsSection } from "../InferenceParamsSection";
import type { ParamSpec, InferenceParams } from "@/types/extended-api";

const mockParamSpecs: Record<string, ParamSpec> = {
  temperature: { name: "temperature", type: "float", min: 0, max: 2, default: 0.7, step: 0.05, label: "Temperature", description: "Controls randomness" },
  top_p: { name: "top_p", type: "float", min: 0, max: 1, default: 0.9, step: 0.05, label: "Top P", description: "Nucleus sampling" },
  top_k: { name: "top_k", type: "int", min: -1, max: 200, default: -1, step: 1, label: "Top K", description: "Token candidates" },
  max_tokens: { name: "max_tokens", type: "int", min: 1, max: 131072, default: 4096, step: 1, label: "Max Tokens", description: "Maximum output tokens" },
};

const mockPresets = {
  precise: { temperature: 0.1, top_p: 0.5, top_k: 40, max_tokens: 4096 },
  balanced: { temperature: 0.7, top_p: 0.9, top_k: -1, max_tokens: 4096 },
  creative: { temperature: 1.0, top_p: 0.95, top_k: -1, max_tokens: 4096 },
};

const vllmServerParamSpecs: Record<string, ParamSpec> = {
  gpu_memory_utilization: { name: "gpu_memory_utilization", type: "float", min: 0.1, max: 0.99, default: 0.9, step: 0.05, label: "GPU Memory Utilization", description: "Fraction of GPU memory" },
  tensor_parallel_size: { name: "tensor_parallel_size", type: "int", min: 1, max: 8, default: 1, step: 1, label: "Tensor Parallel Size", description: "Number of GPUs" },
};

const defaultProps = {
  capability: "llm" as const,
  provider: "openai",
  params: { temperature: 0.7, top_p: 0.9 } as InferenceParams,
  supportedParams: ["temperature", "top_p"],
  paramSpecs: mockParamSpecs,
  presets: mockPresets,
  onParamsChange: vi.fn(),
  onReset: vi.fn(),
};

/** Helper to expand the collapsible trigger */
function expandSection() {
  const trigger = screen.getByText("Inference Parameters");
  fireEvent.click(trigger);
}

describe("InferenceParamsSection", () => {
  it("renders supported params only", () => {
    render(<InferenceParamsSection {...defaultProps} />);
    expandSection();

    // Should render Temperature and Top P
    expect(screen.getByText("Temperature")).toBeInTheDocument();
    expect(screen.getByText("Top P")).toBeInTheDocument();

    // Should NOT render Top K or Max Tokens (not in supportedParams)
    expect(screen.queryByText("Top K")).not.toBeInTheDocument();
    expect(screen.queryByText("Max Tokens")).not.toBeInTheDocument();
  });

  it("preset selection fills values", () => {
    const onParamsChange = vi.fn();
    render(
      <InferenceParamsSection
        {...defaultProps}
        onParamsChange={onParamsChange}
        supportedParams={["temperature", "top_p", "top_k", "max_tokens"]}
        params={{ temperature: 0.7, top_p: 0.9, top_k: -1, max_tokens: 4096 }}
      />
    );
    expandSection();

    // Find and click the preset selector, select "precise"
    const presetTrigger = screen.getByRole("combobox");
    fireEvent.click(presetTrigger);

    const preciseOption = screen.getByText("Precise");
    fireEvent.click(preciseOption);

    // Should call onParamsChange with precise preset values
    expect(onParamsChange).toHaveBeenCalledWith(
      expect.objectContaining({
        temperature: 0.1,
        top_p: 0.5,
        top_k: 40,
        max_tokens: 4096,
      })
    );
  });

  it("manual change shows Custom preset", () => {
    // Params that don't match any preset
    render(
      <InferenceParamsSection
        {...defaultProps}
        params={{ temperature: 0.42, top_p: 0.77 }}
      />
    );
    expandSection();

    // The preset dropdown should show "Custom"
    const presetTrigger = screen.getByRole("combobox");
    expect(presetTrigger).toHaveTextContent("Custom");
  });

  it("reset calls onReset", () => {
    const onReset = vi.fn();
    render(<InferenceParamsSection {...defaultProps} onReset={onReset} />);
    expandSection();

    const resetBtn = screen.getByText("Reset to Defaults");
    fireEvent.click(resetBtn);

    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("vLLM advanced hidden for non-vLLM provider", () => {
    render(
      <InferenceParamsSection
        {...defaultProps}
        provider="openai"
        vllmServerParamSpecs={vllmServerParamSpecs}
        vllmServerParams={{ gpu_memory_utilization: 0.9 }}
      />
    );
    expandSection();

    expect(screen.queryByText("Advanced Parameters")).not.toBeInTheDocument();
    expect(screen.queryByText("Requires vLLM restart")).not.toBeInTheDocument();
  });

  it("vLLM advanced visible for vLLM provider", () => {
    render(
      <InferenceParamsSection
        {...defaultProps}
        provider="vllm"
        vllmServerParamSpecs={vllmServerParamSpecs}
        vllmServerParams={{ gpu_memory_utilization: 0.9, tensor_parallel_size: 1 }}
        onVllmServerParamsChange={vi.fn()}
      />
    );
    expandSection();

    expect(screen.getByText("Advanced Parameters")).toBeInTheDocument();
    expect(screen.getByText("Requires vLLM restart")).toBeInTheDocument();
  });

  it("embedding renders nothing when supportedParams is empty", () => {
    const { container } = render(
      <InferenceParamsSection
        {...defaultProps}
        capability="embedding"
        supportedParams={[]}
        params={{}}
      />
    );

    // Component should render null (empty)
    expect(container.innerHTML).toBe("");
  });
});
