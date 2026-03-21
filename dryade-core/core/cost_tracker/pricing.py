"""Pricing service for database-backed model cost management.

Syncs 1500+ models from litellm.model_cost with support for admin-editable
manual overrides. Manual overrides are preserved during litellm sync.
"""

from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.database.models import ModelPricing
from core.logs import get_logger

logger = get_logger(__name__)

class PricingService:
    """DB-backed pricing with litellm auto-sync and manual overrides."""

    def get_all(
        self,
        db: Session,
        search: str | None = None,
        provider: str | None = None,
        source: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ModelPricing], int]:
        """Get pricing entries with optional filters."""
        query = db.query(ModelPricing)
        if search:
            query = query.filter(ModelPricing.model_name.ilike(f"%{search}%"))
        if provider:
            query = query.filter(ModelPricing.provider == provider)
        if source:
            query = query.filter(ModelPricing.source == source)

        total = query.count()
        items = query.order_by(ModelPricing.model_name).offset(offset).limit(limit).all()
        return items, total

    def get_by_model(self, db: Session, model_name: str) -> ModelPricing | None:
        """Get pricing for a specific model."""
        return db.query(ModelPricing).filter(ModelPricing.model_name == model_name).first()

    def update_pricing(
        self,
        db: Session,
        model_name: str,
        input_cost: float,
        output_cost: float,
        updated_by: str,
    ) -> ModelPricing:
        """Update pricing for a model (manual override). Sets source='manual'."""
        existing = self.get_by_model(db, model_name)
        if existing:
            existing.input_cost_per_token = input_cost
            existing.output_cost_per_token = output_cost
            existing.source = "manual"
            existing.updated_by = updated_by
            existing.updated_at = datetime.now(UTC)
        else:
            existing = ModelPricing(
                model_name=model_name,
                input_cost_per_token=input_cost,
                output_cost_per_token=output_cost,
                source="manual",
                updated_by=updated_by,
            )
            db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    def sync_from_litellm(self, db: Session, updated_by: str = "system") -> dict:
        """Sync all models from litellm.model_cost to DB.

        Returns {"synced": count, "skipped_manual": count, "total": count}.
        Manual overrides (source='manual') are preserved during sync.
        """
        try:
            import litellm
        except ImportError:
            raise ImportError("litellm is not installed")

        model_cost = getattr(litellm, "model_cost", {})
        if not model_cost:
            return {"synced": 0, "skipped_manual": 0, "total": 0}

        synced = 0
        skipped_manual = 0
        batch_count = 0

        for model_name, info in model_cost.items():
            existing = self.get_by_model(db, model_name)

            if existing and existing.source == "manual":
                skipped_manual += 1
                continue

            input_cost = info.get("input_cost_per_token", 0.0) or 0.0
            output_cost = info.get("output_cost_per_token", 0.0) or 0.0
            provider = info.get("litellm_provider", None)

            if existing:
                existing.input_cost_per_token = input_cost
                existing.output_cost_per_token = output_cost
                existing.provider = provider
                existing.source = "litellm"
                existing.updated_by = updated_by
                existing.updated_at = datetime.now(UTC)
            else:
                db.add(
                    ModelPricing(
                        model_name=model_name,
                        provider=provider,
                        input_cost_per_token=input_cost,
                        output_cost_per_token=output_cost,
                        source="litellm",
                        updated_by=updated_by,
                    )
                )

            synced += 1
            batch_count += 1

            if batch_count >= 100:
                db.commit()
                batch_count = 0

        if batch_count > 0:
            db.commit()

        total = len(model_cost)
        logger.info(
            f"Pricing sync: {synced} synced, {skipped_manual} manual skipped, {total} total"
        )
        return {"synced": synced, "skipped_manual": skipped_manual, "total": total}

    def get_stats(self, db: Session) -> dict:
        """Get pricing statistics: total models, by source, by provider."""
        total = db.query(func.count(ModelPricing.id)).scalar() or 0

        source_rows = (
            db.query(ModelPricing.source, func.count(ModelPricing.id))
            .group_by(ModelPricing.source)
            .all()
        )
        by_source = {row[0]: row[1] for row in source_rows}

        provider_rows = (
            db.query(ModelPricing.provider, func.count(ModelPricing.id))
            .group_by(ModelPricing.provider)
            .all()
        )
        by_provider = {(row[0] or "unknown"): row[1] for row in provider_rows}

        return {
            "total_models": total,
            "by_source": by_source,
            "by_provider": by_provider,
        }
