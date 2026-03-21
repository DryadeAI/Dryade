"""Cost Tracking Extension for CrewAI.

Tracks LLM token usage and estimated costs per agent/task/crew.
Target: ~100 LOC
"""

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Cost per 1M tokens (fallback when litellm.model_cost is unavailable)
DEFAULT_COSTS = {
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    # Anthropic
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "claude-sonnet-4": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.00},
    "claude-opus-4": {"input": 15.00, "output": 75.00},
    "claude-3-opus": {"input": 15.00, "output": 75.00},
    "claude-3-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-haiku": {"input": 0.25, "output": 1.25},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku": {"input": 0.80, "output": 4.00},
    # Local
    "mistral": {"input": 0.00, "output": 0.00},
    "ollama": {"input": 0.00, "output": 0.00},
    "vllm": {"input": 0.00, "output": 0.00},
}

@dataclass
class CostRecord:
    """Single in-memory cost record for fast aggregation."""

    timestamp: str
    model: str
    agent: str
    task_id: str | None
    conversation_id: str | None
    user_id: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    # Phase 72: Template cost dimension
    template_id: int | None = None
    template_version_id: int | None = None

@dataclass
class CostTracker:
    """Track LLM costs per agent/task/crew."""

    records: list[CostRecord] = field(default_factory=list)
    costs: dict[str, dict[str, float]] = field(default_factory=lambda: DEFAULT_COSTS.copy())

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        agent: str = "unknown",
        task_id: str | None = None,
        conversation_id: str | None = None,
        user_id: str | None = None,
        template_id: int | None = None,
        template_version_id: int | None = None,
    ):
        """Record an LLM call to both memory and database."""
        cost_config = self._get_cost_config(model)
        cost = (input_tokens / 1_000_000) * cost_config["input"] + (
            output_tokens / 1_000_000
        ) * cost_config["output"]

        self.records.append(
            CostRecord(
                timestamp=datetime.now(UTC).isoformat(),
                model=model,
                agent=agent,
                task_id=task_id,
                conversation_id=conversation_id,
                user_id=user_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                template_id=template_id,
                template_version_id=template_version_id,
            )
        )

        self._persist_to_db(
            model=model,
            agent=agent,
            task_id=task_id,
            conversation_id=conversation_id,
            user_id=user_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            template_id=template_id,
            template_version_id=template_version_id,
        )

    def _persist_to_db(
        self,
        model: str,
        agent: str,
        task_id: str | None,
        conversation_id: str | None,
        user_id: str | None,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        template_id: int | None = None,
        template_version_id: int | None = None,
    ):
        """Persist cost record to database."""
        try:
            from core.database.models import CostRecord as DBCostRecord
            from core.database.session import get_session

            with get_session() as db:
                db_record = DBCostRecord(
                    model=model,
                    agent=agent,
                    task_id=task_id,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    template_id=template_id,
                    template_version_id=template_version_id,
                )
                db.add(db_record)
                db.commit()
        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"Failed to persist cost record: {e}")

    def _get_cost_config(self, model: str) -> dict[str, float]:
        """Get cost config for a model.

        Lookup order:
        1. DB model_pricing table (manual overrides + litellm synced)
        2. litellm.model_cost (runtime, if installed)
        3. Hardcoded DEFAULT_COSTS
        4. Prefix match (e.g. "ollama/llama3.1" -> "ollama")
        5. Free (local model assumption)
        """
        db_pricing = self._get_db_pricing(model)
        if db_pricing:
            return db_pricing

        try:
            import litellm

            cost_info = litellm.model_cost.get(model)
            if cost_info:
                return {
                    "input": cost_info.get("input_cost_per_token", 0) * 1_000_000,
                    "output": cost_info.get("output_cost_per_token", 0) * 1_000_000,
                }
        except Exception:
            pass

        if model in self.costs:
            return self.costs[model]

        prefix = model.split("/")[0] if "/" in model else model
        if prefix in self.costs:
            return self.costs[prefix]

        return {"input": 0.00, "output": 0.00}

    def _get_db_pricing(self, model: str) -> dict[str, float] | None:
        """Look up pricing from the model_pricing DB table."""
        try:
            from core.database.models import ModelPricing
            from core.database.session import get_session

            with get_session() as db:
                row = db.query(ModelPricing).filter(ModelPricing.model_name == model).first()
                if row and (row.input_cost_per_token or row.output_cost_per_token):
                    return {
                        "input": row.input_cost_per_token * 1_000_000,
                        "output": row.output_cost_per_token * 1_000_000,
                    }
        except Exception:
            pass
        return None

    def get_summary(self) -> dict[str, Any]:
        """Get cost summary."""
        if not self.records:
            return {
                "total_cost_usd": 0.0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "by_agent": {},
                "by_model": {},
                "by_template": {},
                "record_count": 0,
            }

        total_cost = sum(r.cost_usd for r in self.records)
        total_input = sum(r.input_tokens for r in self.records)
        total_output = sum(r.output_tokens for r in self.records)

        by_agent: dict[str, float] = {}
        by_model: dict[str, float] = {}
        by_template: dict[int, float] = {}

        for r in self.records:
            by_agent[r.agent] = by_agent.get(r.agent, 0) + r.cost_usd
            by_model[r.model] = by_model.get(r.model, 0) + r.cost_usd
            if r.template_id is not None:
                by_template[r.template_id] = by_template.get(r.template_id, 0) + r.cost_usd

        return {
            "total_cost_usd": round(total_cost, 6),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "by_agent": by_agent,
            "by_model": by_model,
            "by_template": by_template,
            "record_count": len(self.records),
        }

    def get_records(self, limit: int = 100) -> list[dict]:
        """Get recent cost records from in-memory storage."""
        return [
            {
                "timestamp": r.timestamp,
                "model": r.model,
                "agent": r.agent,
                "task_id": r.task_id,
                "conversation_id": r.conversation_id,
                "user_id": r.user_id,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cost_usd": r.cost_usd,
                "template_id": r.template_id,
                "template_version_id": r.template_version_id,
            }
            for r in self.records[-limit:]
        ]

    def clear(self):
        """Clear all records."""
        self.records.clear()

# Global tracker instance
_cost_tracker: CostTracker | None = None
_lock = threading.Lock()

def get_cost_tracker() -> CostTracker:
    """Get or create global cost tracker."""
    global _cost_tracker
    with _lock:
        if _cost_tracker is None:
            _cost_tracker = CostTracker()
    return _cost_tracker

def record_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    agent: str = "unknown",
    task_id: str | None = None,
    conversation_id: str | None = None,
    user_id: str | None = None,
    template_id: int | None = None,
    template_version_id: int | None = None,
):
    """Convenience function to record cost."""
    get_cost_tracker().record(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        agent=agent,
        task_id=task_id,
        conversation_id=conversation_id,
        user_id=user_id,
        template_id=template_id,
        template_version_id=template_version_id,
    )

def get_cost_summary() -> dict[str, Any]:
    """Convenience function to get cost summary."""
    return get_cost_tracker().get_summary()
