"""
model_advisor.py — Standalone CLI: hardware detection + model scoring + recommendations.

Usage:
    python model_advisor.py [--backend vllm|ollama|auto] [--tool-calling] [--top N] [--json]

Dependencies:
    - stdlib only (argparse, json, pathlib, sys)
    - psutil (via hardware.py — confirmed installed 5.9.8)
    - litellm (optional — used for context-window enrichment if installed)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add this directory to path so we can import sibling modules
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

from hardware import detect_hardware  # noqa: E402
from scorer import score_models  # noqa: E402

def _load_models(models_path: Path) -> list[dict]:
    """Load models.json, exit with helpful error if not found."""
    if not models_path.exists():
        print(
            f"Error: models.json not found at {models_path}\n"
            "Make sure you are running from the community-tools/model-advisor directory\n"
            "or that models.json is present next to this script.",
            file=sys.stderr,
        )
        sys.exit(1)
    with models_path.open() as fh:
        return json.load(fh)

def _enrich_with_litellm(results: list[dict], pref_backend: str) -> dict[str, bool]:
    """
    Best-effort litellm context window enrichment.

    Returns a dict mapping model id -> enriched (True if litellm data was used).
    Silently skips if litellm is not installed or the model key is not found.
    """
    enriched: dict[str, bool] = {}
    try:
        import litellm  # type: ignore

        for model in results:
            key = None
            if pref_backend == "ollama" and model.get("ollama_tag"):
                key = f"ollama/{model['ollama_tag']}"
            if key and key in litellm.model_cost:
                entry = litellm.model_cost[key]
                new_ctx = entry.get("max_input_tokens")
                if new_ctx:
                    model["capabilities"]["context_window"] = new_ctx
                    enriched[model["id"]] = True
            else:
                enriched[model["id"]] = False
    except ImportError:
        pass  # litellm not available — use models.json data only
    return enriched

def _format_hardware(hw: dict) -> str:
    lines = ["Hardware detected:"]
    lines.append(f"  RAM: {hw['total_ram_gb']} GB total ({hw['available_ram_gb']} GB available)")
    if hw.get("gpu_name"):
        if hw["unified_memory"]:
            lines.append(f"  GPU: {hw['gpu_name']} ({hw['vram_gb']} GB unified memory)")
        else:
            lines.append(f"  GPU: {hw['gpu_name']} ({hw['vram_gb']} GB VRAM)")
        lines.append(
            f"  Backend: {hw['backend']} ({'unified memory' if hw['unified_memory'] else 'discrete GPU'})"
        )
    else:
        lines.append("  GPU: none detected")
        lines.append("  Backend: CPU-only")
    return "\n".join(lines)

def _speed_label(tier: str) -> str:
    return {"fast": "[fast]", "medium": "[medium]", "slow": "[slow]"}.get(tier, "[?]")

def _format_results(
    results: list[dict],
    hw: dict,
    pref_backend: str,
    enriched: dict[str, bool],
    show_tool_calling_only: bool,
) -> str:
    if not results:
        return "No models found matching your criteria."

    si = results[0]["score_info"]
    # precision already includes the backend (e.g. "vllm/bfloat16" or "ollama/q4km")
    precision = si["precision"]
    usable_gb = si["memory_available_gb"]

    lines: list[str] = [
        f"Top {len(results)} recommendations for {precision} on {usable_gb} GB usable:",
        "",
    ]

    for i, model in enumerate(results, 1):
        si = model["score_info"]
        name = model["name"]
        speed = _speed_label(model.get("speed_tier", ""))
        tool_tag = "  [tool_calling]" if model.get("capabilities", {}).get("tool_calling") else ""
        mem_req = si["memory_required_gb"]

        pull_key = (
            f"ollama pull {model['ollama_tag']}"
            if pref_backend == "ollama" and model.get("ollama_tag")
            else f"hf: {model.get('hf_repo', model['id'])}"
        )

        ctx = model.get("capabilities", {}).get("context_window")
        ctx_str = ""
        if ctx:
            ctx_source = " (litellm)" if enriched.get(model["id"]) else ""
            ctx_str = f"  context: {ctx:,}{ctx_source}"

        lines.append(f"  {i}. {name:<38} {speed}{tool_tag}  requires {mem_req} GB")
        lines.append(f"     {pull_key}{ctx_str}")
        lines.append("")

    tips: list[str] = []
    if pref_backend == "vllm":
        tips.append("Tip: Use --backend ollama to see Ollama/GGUF recommendations.")
    else:
        tips.append("Tip: Use --backend vllm to see vLLM/bfloat16 recommendations.")
    if not show_tool_calling_only:
        tips.append("Tip: Use --tool-calling to filter to tool-calling capable models only.")
    lines.extend(tips)

    return "\n".join(lines)

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recommend LLM models that fit your hardware.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--backend",
        choices=["vllm", "ollama", "auto"],
        default="auto",
        help="Backend preference (default: auto — picks vllm for CUDA, ollama otherwise)",
    )
    parser.add_argument(
        "--tool-calling",
        action="store_true",
        default=False,
        help="Only show models with confirmed tool calling support",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        metavar="N",
        help="Number of recommendations to show (default: 5)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output raw JSON instead of formatted text",
    )
    args = parser.parse_args()

    # 1. Detect hardware
    try:
        hw = detect_hardware()
    except Exception as exc:
        print(f"Warning: hardware detection failed ({exc}), using degraded mode.", file=sys.stderr)
        import psutil  # type: ignore

        vm = psutil.virtual_memory()
        hw = {
            "total_ram_gb": round(vm.total / (1024**3), 2),
            "available_ram_gb": round(vm.available / (1024**3), 2),
            "cpu_cores": 1,
            "gpu_name": None,
            "vram_gb": 0.0,
            "unified_memory": False,
            "backend": "CPU",
            "detection_notes": [f"degraded mode: {exc}"],
        }

    # 2. Load models.json
    models_path = _HERE / "models.json"
    models = _load_models(models_path)

    # 3. Score
    results = score_models(
        models=models,
        hardware=hw,
        backend_preference=args.backend,
        require_tool_calling=args.tool_calling,
        max_results=args.top,
    )

    # Determine effective backend for output labels
    pref_backend: str
    if args.backend == "auto":
        pref_backend = "vllm" if hw.get("backend") == "CUDA" else "ollama"
    else:
        pref_backend = args.backend

    # 4. litellm enrichment (best-effort)
    enriched = _enrich_with_litellm(results, pref_backend)

    # 5. Output
    if args.json:
        output = {
            "hardware": hw,
            "recommendations": results,
            "query": {
                "backend": args.backend,
                "tool_calling": args.tool_calling,
                "top": args.top,
            },
        }
        print(json.dumps(output, indent=2))
    else:
        print("=== Dryade Model Advisor ===")
        print()
        print(_format_hardware(hw))
        print()
        print(_format_results(results, hw, pref_backend, enriched, args.tool_calling))

if __name__ == "__main__":
    main()
