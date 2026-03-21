---
title: Edge Hardware Deployment
sidebar_position: 5
description: Run Dryade with local LLMs on NVIDIA Jetson, DGX Spark, and other edge devices
---

# Edge Hardware Deployment

Dryade is designed to run on edge hardware, bringing AI orchestration directly to your infrastructure. This guide covers deploying with local LLMs on NVIDIA Jetson, DGX Spark, and similar devices.

## Why Edge Deployment?

- **Data sovereignty** -- Your data never leaves your hardware
- **Low latency** -- No network round-trip to cloud APIs
- **Cost control** -- No per-token charges after hardware investment
- **Offline capable** -- Works without internet connectivity
- **Compliance** -- Meet data residency requirements by keeping everything on-premises

## Supported Hardware

### NVIDIA DGX Spark (GB10 Grace Blackwell)

The DGX Spark is a desktop-class AI workstation with exceptional capabilities:

- **GPU:** NVIDIA Blackwell architecture with 6144 CUDA cores
- **Memory:** 128 GB unified LPDDR5x (shared between CPU and GPU)
- **Compute:** Native FP4 and FP8 tensor cores for efficient inference
- **Platform:** ARM-based (Grace CPU), reports as `Linux tegra`

The large unified memory pool makes DGX Spark ideal for running models up to 70B parameters without quantization.

### NVIDIA Jetson Series

| Device | GPU Memory | Recommended Models |
|--------|-----------|-------------------|
| Jetson Orin Nano (8 GB) | 8 GB shared | Qwen3-4B, Phi-3 Mini |
| Jetson Orin NX (16 GB) | 16 GB shared | Qwen3-8B, Llama 3.2 8B |
| Jetson AGX Orin (32-64 GB) | 32-64 GB shared | Qwen3-14B, Llama 3.1 70B (quantized) |

### Other NVIDIA GPUs

Any NVIDIA GPU with Compute Capability >= 7.0 (Volta architecture or newer) works with vLLM:

| GPU | VRAM | Recommended Models |
|-----|------|-------------------|
| RTX 3060 (12 GB) | 12 GB | Qwen3-8B (4-bit), Ministral-8B (4-bit) |
| RTX 4090 (24 GB) | 24 GB | Qwen3-8B, Ministral-8B, Llama 3.1 8B |
| A100 (40-80 GB) | 40-80 GB | Llama 3.1 70B, DeepSeek-V3 (quantized) |

## vLLM Setup

[vLLM](https://docs.vllm.ai/) is the recommended inference engine for local model serving. It provides an OpenAI-compatible API that Dryade connects to natively.

### Docker Setup (Recommended)

```bash
# Start vLLM with Docker
docker run --gpus all \
  --ipc=host \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -p 8000:8000 \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen3-8B \
  --served-model-name local-llm \
  --gpu-memory-utilization 0.85 \
  --max-model-len 8192
```

> **Important:** The `--ipc=host` flag (or `--shm-size=8g`) is mandatory. PyTorch uses shared memory for tensor operations, and the default Docker shared memory (64 MB) is insufficient.

### Docker Compose Integration

Add vLLM to your Dryade `docker-compose.yml`:

```yaml
services:
  vllm:
    image: vllm/vllm-openai:latest
    runtime: nvidia
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    ipc: host
    volumes:
      - vllm-cache:/root/.cache/huggingface
    environment:
      - VLLM_MODEL=${VLLM_MODEL:-Qwen/Qwen3-8B}
    command: >
      --model ${VLLM_MODEL:-Qwen/Qwen3-8B}
      --served-model-name local-llm
      --gpu-memory-utilization 0.85
      --max-model-len 8192
    ports:
      - "8000:8000"

volumes:
  vllm-cache:
```

Then configure Dryade to connect:

```env
DRYADE_LLM_MODE=vllm
DRYADE_LLM_BASE_URL=http://vllm:8000/v1
DRYADE_LLM_MODEL=local-llm
```

## Memory Management

### GPU Memory Utilization

The `--gpu-memory-utilization` flag controls how much GPU memory vLLM reserves. For edge devices with unified memory, this directly impacts system stability:

| Setting | Use Case |
|---------|----------|
| `0.7` | Conservative -- leaves room for other GPU tasks |
| `0.85` | Balanced -- recommended starting point |
| `0.9` | Aggressive -- maximum model capacity, minimal headroom |

**For DGX Spark and Jetson** (unified memory): Start with `0.85` and increase to `0.9` if stable. The unified memory architecture means GPU memory allocation reduces available system RAM.

### Max Model Length

The `--max-model-len` flag caps the context window size. Longer contexts use more memory:

```bash
# For 8 GB devices
--max-model-len 4096

# For 16 GB devices
--max-model-len 8192

# For 32+ GB devices
--max-model-len 16384

# For DGX Spark (128 GB)
--max-model-len 32768
```

## Recommended Models

### Best Models for Tool Calling

Dryade's orchestration relies on structured tool calling. These models have been tested and work reliably:

| Model | Parameters | Min VRAM | Tool Calling | Notes |
|-------|-----------|----------|--------------|-------|
| **Qwen3-8B** | 8B | 16 GB | Excellent | Best overall for edge. Hermes-style tool calls. |
| **Ministral-8B-Instruct** | 8B | 16 GB | Excellent | Strong tool calling. Use Instruct variant (not Reasoning). |
| **Llama 3.2 8B** | 8B | 16 GB | Good | Solid general-purpose model. |
| **Qwen3-4B** | 4B | 8 GB | Good | Best for 8 GB devices. |
| **DeepSeek-V3** | Large | 80+ GB | Excellent | Best quality, requires multi-GPU or large memory. |

> **Tip:** Avoid "Reasoning" variants of models (e.g., Ministral-3-Reasoning) for tool calling -- they have known compatibility issues with structured outputs.

### Quantization for Constrained Devices

When VRAM is limited, use quantized models:

```bash
# AWQ quantization (recommended)
--model Qwen/Qwen3-8B-AWQ
--quantization awq

# GPTQ quantization
--model TheBloke/Llama-2-7B-GPTQ
--quantization gptq
```

**AWQ vs GPTQ:**
- **AWQ** -- Generally better quality at the same compression. Recommended default.
- **GPTQ** -- Wider model availability. Slightly faster inference on some hardware.

Both reduce memory usage by roughly 50-75% compared to FP16, with minimal quality loss for 4-bit quantization.

## Jetson-Specific Setup

### Prerequisites

1. **JetPack 6.0+** with CUDA 12.x
2. **NVIDIA Container Toolkit** for Jetson:
   ```bash
   sudo apt-get install nvidia-container-toolkit
   sudo systemctl restart docker
   ```

### Container Image

Use the official vLLM image. On Jetson (ARM64), ensure you pull the correct architecture:

```bash
docker pull vllm/vllm-openai:latest
```

### Performance Tuning

```bash
# Jetson Orin NX (16 GB) example
docker run --gpus all --ipc=host \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -p 8000:8000 \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen3-8B \
  --served-model-name local-llm \
  --gpu-memory-utilization 0.85 \
  --max-model-len 4096 \
  --enforce-eager
```

> **Note:** `--enforce-eager` disables CUDA graphs, which can cause issues on Jetson. This reduces throughput slightly but improves stability.

## DGX Spark Configuration

The DGX Spark's 128 GB unified memory enables running large models that typically require multi-GPU setups:

```bash
# DGX Spark: Run 70B model
docker run --gpus all --ipc=host \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -p 8000:8000 \
  vllm/vllm-openai:latest \
  --model meta-llama/Llama-3.1-70B-Instruct \
  --served-model-name local-llm \
  --gpu-memory-utilization 0.85 \
  --max-model-len 16384
```

**DGX Spark tips:**
- The Grace Blackwell chip supports native FP4 inference -- check model availability in FP4 format for maximum efficiency
- Use `--gpu-memory-utilization 0.85-0.9` to leverage the large memory pool
- Monitor system RAM alongside GPU usage since memory is shared
- vLLM's KV-cache will automatically scale to fill available memory

## Monitoring

### Check vLLM Status

```bash
# Health check
curl http://localhost:8000/health

# List loaded models
curl http://localhost:8000/v1/models

# GPU memory usage
nvidia-smi
```

### Dryade Health Check

```bash
# Full health including LLM connectivity
curl http://localhost:8080/health/detailed
```

The health endpoint shows whether Dryade can reach your vLLM instance and the current model status.

## Troubleshooting

### "CUDA out of memory"

Reduce `--gpu-memory-utilization` or `--max-model-len`, or use a quantized model:

```bash
--gpu-memory-utilization 0.7
--max-model-len 4096
--quantization awq
```

### "Shared memory error" or "Bus error"

Add `--ipc=host` to your Docker run command, or set `--shm-size=8g`.

### "Model too large"

The model does not fit in available memory. Options:
1. Use a smaller model (8B instead of 70B)
2. Use quantization (AWQ or GPTQ)
3. Reduce `--max-model-len`

### Slow first response

vLLM compiles CUDA kernels on first use. The first request after startup is slower. Subsequent requests will be fast.
