"""
scorer.py — Filter and rank models from models.json given detected hardware.

Public API:
    score_models(models, hardware, backend_preference, require_tool_calling, max_results) -> list[dict]

No external dependencies beyond stdlib — litellm enrichment happens in model_advisor.py only.
"""

from __future__ import annotations

def score_models(
    models: list[dict],
    hardware: dict,
    backend_preference: str = "auto",  # "vllm", "ollama", or "auto"
    require_tool_calling: bool = False,
    max_results: int = 5,
) -> list[dict]:
    """
    Filter models that fit in available memory, rank by quality + capability.

    Returns up to max_results model dicts, each with an added 'score_info' key.

    Scoring factors (higher is better):
    - params_score: 0-40 points proportional to model size relative to largest feasible model
    - tool_calling: +30 points if capabilities.tool_calling == True
    - speed_tier: fast=20, medium=10, slow=0
    - memory_headroom: +10 points if model fits in less than 50% of usable memory
    """
    # Step 1: Determine available memory for sizing
    if hardware.get("unified_memory"):
        # Tegra / Apple Silicon: use total RAM but leave 20% headroom for OS
        usable_gb = hardware["total_ram_gb"] * 0.80
    elif hardware.get("vram_gb", 0) > 0:
        # Discrete GPU: use VRAM; can also CPU-offload (not modeled in MVP)
        usable_gb = hardware["vram_gb"] * 0.90
    else:
        # CPU-only: use available RAM with 20% headroom
        usable_gb = hardware["available_ram_gb"] * 0.80

    # Step 2: Determine memory key from backend_preference
    backend = hardware.get("backend", "CPU")
    if backend_preference == "vllm" or (backend_preference == "auto" and backend == "CUDA"):
        mem_key = "vllm_bfloat16_gb"
        fallback_key = "vllm_fp8_gb"
        pref_backend = "vllm"
    else:
        # ollama
        mem_key = "ollama_q4km_gb"
        fallback_key = "ollama_q8_gb"
        pref_backend = "ollama"

    # Step 3: Filter to models that fit
    feasible: list[tuple[dict, float]] = []
    for m in models:
        mem_needed = m["memory"].get(mem_key) or m["memory"].get(fallback_key)
        if mem_needed is None:
            continue
        if mem_needed <= usable_gb:
            # Check backend compatibility
            if pref_backend in m.get("backends", []):
                feasible.append((m, mem_needed))

    # Step 4: Apply tool_calling filter early (before scoring) so params_score
    # normalizes against the feasible+filtered pool only
    if require_tool_calling:
        feasible = [
            (m, mem) for m, mem in feasible if m.get("capabilities", {}).get("tool_calling")
        ]

    if not feasible:
        return []

    # Step 5: Score each feasible model
    max_params = max(m["params_b"] for m, _ in feasible)

    _speed_points = {"fast": 20, "medium": 10, "slow": 0}

    # Determine the actual memory key used (mem_key or fallback)
    def _resolve_mem_key(m: dict) -> str:
        return mem_key if m["memory"].get(mem_key) is not None else fallback_key

    scored: list[dict] = []
    for m, mem_needed in feasible:
        # params_score: normalize against max feasible params_b → 0-40 points
        params_score = (m["params_b"] / max_params) * 40.0 if max_params > 0 else 0.0

        # tool_calling bonus
        tool_bonus = 30.0 if m.get("capabilities", {}).get("tool_calling") else 0.0

        # speed_tier bonus
        speed_bonus = float(_speed_points.get(m.get("speed_tier", "slow"), 0))

        # memory_headroom: +10 if fits in less than 50% of usable memory
        headroom_bonus = 10.0 if mem_needed < usable_gb * 0.5 else 0.0

        total_score = params_score + tool_bonus + speed_bonus + headroom_bonus

        # Attach score_info to a copy to avoid mutating the source list
        result = dict(m)
        used_key = _resolve_mem_key(m)
        precision_label = used_key.replace("_gb", "").replace("_", "/")
        result["score_info"] = {
            "total_score": round(total_score, 2),
            "memory_required_gb": round(mem_needed, 1),
            "memory_available_gb": round(usable_gb, 1),
            "backend_used": pref_backend,
            "precision": precision_label,
        }
        scored.append(result)

    # Step 6: Sort by score descending, return top N
    scored.sort(key=lambda x: x["score_info"]["total_score"], reverse=True)
    return scored[:max_results]
