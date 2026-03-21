"""
hardware.py — System hardware detection for the model advisor.

Public API:
    detect_hardware() -> dict

Dependencies:
    - psutil (required, confirmed installed: 5.9.8)
    - pynvml (optional, graceful ImportError if not installed)
    - nvidia-smi (optional subprocess fallback for Tegra/unified memory)

On Tegra (NVIDIA DGX Spark / Grace Blackwell), pynvml returns 0 bytes for
VRAM because CPU and GPU share unified LPDDR5x memory. The fallback uses
nvidia-smi to detect this condition and uses psutil.virtual_memory().total
as the unified memory pool size.
"""

import subprocess

import psutil

# TODO: Apple Silicon (system_profiler) - out of scope for MVP
# TODO: AMD GPU (rocm-smi) - out of scope for MVP

def detect_hardware() -> dict:
    """
    Detect system hardware and return a structured summary.

    Returns:
        dict with keys:
            total_ram_gb (float): Total system RAM in GB (rounded to 2dp)
            available_ram_gb (float): Available system RAM in GB (rounded to 2dp)
            cpu_cores (int): Physical CPU cores (logical=False)
            gpu_name (str | None): GPU display name, or None if no GPU detected
            vram_gb (float): GPU VRAM in GB; equals total_ram_gb for unified memory; 0 if no GPU
            unified_memory (bool): True for Tegra/Apple Silicon (CPU+GPU share same pool)
            backend (str): "CUDA", "CPU", or "Metal" (Apple, future)
            detection_notes (list[str]): Human-readable notes about fallbacks used
    """
    notes: list[str] = []

    # --- Baseline CPU/RAM info (always available) ---
    vm = psutil.virtual_memory()
    total_ram_gb = round(vm.total / (1024**3), 2)
    available_ram_gb = round(vm.available / (1024**3), 2)
    cpu_cores = psutil.cpu_count(logical=False) or 1

    # --- GPU detection ---

    # Step 1: pynvml primary path (discrete GPU with real VRAM)
    gpu_name_from_nvml: str | None = None
    try:
        import pynvml  # type: ignore

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode()
        vram_gb = info.total / (1024**3)
        if vram_gb > 0.1:
            # Discrete GPU with real VRAM — all done
            notes.append(f"pynvml detected discrete GPU: {name} ({round(vram_gb, 2)} GB VRAM)")
            return {
                "total_ram_gb": total_ram_gb,
                "available_ram_gb": available_ram_gb,
                "cpu_cores": cpu_cores,
                "gpu_name": name,
                "vram_gb": round(vram_gb, 2),
                "unified_memory": False,
                "backend": "CUDA",
                "detection_notes": notes,
            }
        # vram_gb == 0 → Tegra / unified memory → fall through to Step 2
        gpu_name_from_nvml = name
        notes.append(
            f"pynvml reports 0 VRAM for '{name}' — likely Tegra unified memory, checking nvidia-smi"
        )
    except ImportError:
        notes.append("pynvml not installed — using nvidia-smi fallback")
    except Exception as e:
        notes.append(f"pynvml error ({e}) — using nvidia-smi fallback")

    # Step 2: Tegra/unified memory detection via nvidia-smi
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split(",")
            gpu_name = parts[0].strip() if parts else (gpu_name_from_nvml or "Unknown NVIDIA GPU")
            mem_total_str = parts[1].strip() if len(parts) > 1 else "0"
            try:
                mem_total_mib = float(mem_total_str)
            except ValueError:
                mem_total_mib = 0.0

            if mem_total_mib < 1:
                # 0 MiB or N/A → Tegra unified memory
                notes.append("Tegra unified memory detected: using system RAM as VRAM")
                return {
                    "total_ram_gb": total_ram_gb,
                    "available_ram_gb": available_ram_gb,
                    "cpu_cores": cpu_cores,
                    "gpu_name": gpu_name,
                    "vram_gb": round(total_ram_gb, 2),
                    "unified_memory": True,
                    "backend": "CUDA",
                    "detection_notes": notes,
                }
            else:
                # nvidia-smi reports discrete VRAM (pynvml was missing or failed)
                vram_from_smi = round(mem_total_mib / 1024, 2)
                notes.append(
                    f"nvidia-smi reported discrete GPU: {gpu_name} ({vram_from_smi} GB VRAM)"
                )
                return {
                    "total_ram_gb": total_ram_gb,
                    "available_ram_gb": available_ram_gb,
                    "cpu_cores": cpu_cores,
                    "gpu_name": gpu_name,
                    "vram_gb": vram_from_smi,
                    "unified_memory": False,
                    "backend": "CUDA",
                    "detection_notes": notes,
                }
        else:
            if result.returncode != 0:
                notes.append(f"nvidia-smi exited with code {result.returncode}")
            else:
                notes.append("nvidia-smi returned empty output")
    except FileNotFoundError:
        notes.append("nvidia-smi not found — CPU-only mode")
    except subprocess.TimeoutExpired:
        notes.append("nvidia-smi timed out — CPU-only mode")
    except Exception as e:
        notes.append(f"nvidia-smi error ({e}) — CPU-only mode")

    # Step 3: No GPU detected → CPU-only
    return {
        "total_ram_gb": total_ram_gb,
        "available_ram_gb": available_ram_gb,
        "cpu_cores": cpu_cores,
        "gpu_name": None,
        "vram_gb": 0.0,
        "unified_memory": False,
        "backend": "CPU",
        "detection_notes": notes,
    }

if __name__ == "__main__":
    import json

    print(json.dumps(detect_hardware(), indent=2))
