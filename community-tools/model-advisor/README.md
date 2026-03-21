# Model Advisor

A standalone hardware-aware model recommendation tool. It detects your GPU and RAM, filters
LLM models that fit your memory budget, and ranks them by quality and tool-calling support.
Covers both vLLM (HuggingFace bfloat16) and Ollama (GGUF quantized) inference backends.

No Dryade installation, login, or subscription required. Works offline after `pip install psutil`.

---

## What This Does

Model Advisor reads your hardware (GPU VRAM or system RAM), filters a curated database of
popular open-weight models to those that fit, and ranks them by a score that combines model
size, tool-calling capability, and inference speed tier. The result is an ordered list of
models you can actually run on your machine, with the exact `ollama pull` command or
HuggingFace repo path needed to get started.

---

## Requirements

```
Python 3.9+
pip install psutil           # required
pip install nvidia-ml-py     # optional: improves NVIDIA discrete GPU detection
```

`psutil` is likely already installed if you have Dryade. `nvidia-ml-py` (pynvml) is
optional — the tool falls back to `nvidia-smi` automatically if it is not present.

---

## Usage

```bash
python model_advisor.py                          # auto-detect backend, top 5 models
python model_advisor.py --backend ollama         # Ollama/GGUF recommendations only
python model_advisor.py --backend vllm           # vLLM/HuggingFace recommendations only
python model_advisor.py --tool-calling           # filter to tool-calling capable models
python model_advisor.py --top 10                 # show top 10 instead of 5
python model_advisor.py --json                   # machine-readable JSON output
```

Run from the `community-tools/model-advisor/` directory, or make sure `models.json` is
present next to the script.

### Example output

```
=== Dryade Model Advisor ===

Hardware detected:
  RAM: 122.07 GB total (100.4 GB available)
  GPU: NVIDIA GH100 (122.07 GB unified memory)
  Backend: CUDA (unified memory)

Top 5 recommendations for vllm/bfloat16 on 97.7 GB usable:

  1. DeepSeek-R1-Distill-Qwen-32B      [medium]  [tool_calling]  requires 64.5 GB
     hf: deepseek-ai/DeepSeek-R1-Distill-Qwen-32B

  2. Qwen2.5-72B-Instruct              [slow]    [tool_calling]  requires 72.0 GB
     hf: Qwen/Qwen2.5-72B-Instruct
```

---

## Hardware Support

| Hardware | RAM Detection | GPU Detection | Notes |
|----------|--------------|---------------|-------|
| NVIDIA discrete GPU (RTX 3xxx/4xxx) | psutil | pynvml or nvidia-smi | Full support |
| NVIDIA DGX Spark / Jetson (Tegra unified memory) | psutil (full RAM) | nvidia-smi ATS fallback | Unified memory correctly detected |
| Apple Silicon (M1/M2/M3/M4) | psutil | Not supported | Uses total RAM for sizing |
| AMD GPU | psutil | Not supported | Uses system RAM only; AMD contribution welcome |
| CPU-only (no GPU) | psutil | N/A | CPU-only models recommended |

**DGX Spark note:** On NVIDIA Grace Blackwell (Tegra/ATS), pynvml reports 0 VRAM because
the CPU and GPU share a unified LPDDR5x memory pool. The tool detects this via `nvidia-smi`
and uses total system RAM as the sizing budget — so a 128 GB DGX Spark correctly shows ~122 GB
usable for model loading.

---

## Model Coverage

The model database (`models.json`) contains approximately 40+ curated open-weight models.
Models included: Qwen 2.5 series, Llama 3.x series, Mistral/Ministral, DeepSeek R1/V3,
Gemma 2, Phi-3.5, and others.

Each entry includes:
- Memory requirements for vLLM (bfloat16) and Ollama (Q4_K_M and Q8 quantization)
- Tool-calling capability flag (verified against known-working configurations)
- Speed tier (fast/medium/slow) based on parameter count
- HuggingFace repo and Ollama tag for easy installation

The model database was seeded from the [llmfit](https://github.com/AlexsJones/llmfit)
MIT-licensed model database and extended with vLLM-specific memory fields.

---

## Relationship to Dryade

This is a standalone utility. It does NOT require a Dryade installation, login, or
subscription. It works offline after `pip install psutil`.

If you are using Dryade, Model Advisor helps you choose which model to configure in your
Dryade settings. For Dryade-specific model configuration, see the main Dryade README.

---

## Contributing

New model entries go in `models.json`. The schema is documented at the top of the file:

```json
{
  "id": "unique-slug",
  "name": "Display Name",
  "params_b": 7.0,
  "speed_tier": "fast",
  "backends": ["vllm", "ollama"],
  "hf_repo": "org/repo",
  "ollama_tag": "model:tag",
  "memory": {
    "vllm_bfloat16_gb": 14.5,
    "vllm_fp8_gb": 9.0,
    "ollama_q4km_gb": 4.4,
    "ollama_q8_gb": 7.7
  },
  "capabilities": {
    "tool_calling": true,
    "context_window": 32768
  }
}
```

PRs welcome. Please verify memory figures on real hardware before submitting.
