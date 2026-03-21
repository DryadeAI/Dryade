"""Version-controlled prompt management with rollback.

Phase 115.5: Manages immutable, content-addressed prompt versions
per (prompt_key, model_tier) pair. Supports creating new versions,
activating/deactivating, rollback to parent, and loading active
versions from DB on startup.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

__all__ = [
    "PromptVersion",
    "PromptVersionManager",
    "get_prompt_manager",
]

@dataclass
class PromptVersion:
    """An immutable, content-addressed prompt version.

    Attributes:
        version_id: sha256(content)[:16] -- content-addressed identifier.
        prompt_key: Logical prompt name (e.g. "orchestrate_system", "failure_system").
        model_tier: Target model tier ("frontier", "strong", "moderate", "weak", "all").
        content: Full prompt text.
        is_active: Whether this version is currently active for its (key, tier) pair.
        created_at: When this version was created.
        created_by: Who created it ("bootstrap_optimizer", "manual", "continuous_loop").
        optimization_cycle_id: ID of the optimization cycle that created this version.
        parent_version_id: ID of the parent version for rollback chain.
        metrics_snapshot: Metrics at the time this version was created.
    """

    version_id: str
    prompt_key: str
    model_tier: str
    content: str
    is_active: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    created_by: str = "manual"
    optimization_cycle_id: str | None = None
    parent_version_id: str | None = None
    metrics_snapshot: dict | None = None

class PromptVersionManager:
    """Version-controlled prompt manager with per-tier active tracking.

    In-memory dicts are the source of truth during runtime; the DB
    provides persistence across restarts. On startup, _load_from_db()
    populates from DB. If DB fails, the manager starts empty.

    Key invariant: only one prompt version is active per
    (prompt_key, model_tier) pair at a time.
    """

    def __init__(self):
        # version_id -> PromptVersion
        self._versions: dict[str, PromptVersion] = {}
        # (prompt_key, model_tier) -> version_id
        self._active: dict[tuple[str, str], str] = {}
        self._load_from_db()

    @staticmethod
    def _content_hash(content: str) -> str:
        """Compute a content-addressed version ID.

        Args:
            content: The prompt text.

        Returns:
            sha256(content)[:16] hex string.
        """
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _load_from_db(self) -> None:
        """Load all prompt versions from DB on startup.

        Best-effort: failures are logged but never raised.
        If DB is unavailable, the manager starts empty.
        """
        try:
            from core.database.models import PromptVersionRecord
            from core.database.session import get_session

            with get_session() as session:
                rows = session.query(PromptVersionRecord).all()
                for row in rows:
                    pv = PromptVersion(
                        version_id=row.version_id,
                        prompt_key=row.prompt_key,
                        model_tier=row.model_tier,
                        content=row.content,
                        is_active=row.is_active,
                        created_at=row.created_at or datetime.now(UTC),
                        created_by=row.created_by,
                        optimization_cycle_id=row.optimization_cycle_id,
                        parent_version_id=row.parent_version_id,
                        metrics_snapshot=row.metrics_snapshot,
                    )
                    self._versions[pv.version_id] = pv
                    if pv.is_active:
                        self._active[(pv.prompt_key, pv.model_tier)] = pv.version_id

                logger.debug(
                    "[PROMPT-MGR] Loaded %d versions from DB (%d active)",
                    len(self._versions),
                    len(self._active),
                )
        except Exception:
            logger.debug(
                "[PROMPT-MGR] Failed to load versions from DB, starting empty",
                exc_info=True,
            )

    def create_version(
        self,
        prompt_key: str,
        model_tier: str,
        content: str,
        created_by: str,
        optimization_cycle_id: str | None = None,
        parent_version_id: str | None = None,
        metrics_snapshot: dict | None = None,
    ) -> PromptVersion:
        """Create a new immutable prompt version.

        Does NOT auto-activate -- caller must call activate().

        Args:
            prompt_key: Logical prompt name.
            model_tier: Target model tier.
            content: Full prompt text.
            created_by: Creator identifier.
            optimization_cycle_id: Optional optimization cycle link.
            parent_version_id: Optional parent for rollback chain.
            metrics_snapshot: Optional metrics at creation time.

        Returns:
            The created PromptVersion.
        """
        version_id = self._content_hash(content)

        pv = PromptVersion(
            version_id=version_id,
            prompt_key=prompt_key,
            model_tier=model_tier,
            content=content,
            is_active=False,
            created_at=datetime.now(UTC),
            created_by=created_by,
            optimization_cycle_id=optimization_cycle_id,
            parent_version_id=parent_version_id,
            metrics_snapshot=metrics_snapshot,
        )

        self._versions[version_id] = pv
        self._persist_version(pv)

        logger.debug(
            "[PROMPT-MGR] Created version %s for %s/%s by %s",
            version_id,
            prompt_key,
            model_tier,
            created_by,
        )
        return pv

    def activate(self, version_id: str) -> bool:
        """Activate a prompt version for its (prompt_key, model_tier) pair.

        Deactivates any previously active version for the same pair.

        Args:
            version_id: The version to activate.

        Returns:
            True on success, False if version_id not found.
        """
        pv = self._versions.get(version_id)
        if pv is None:
            logger.warning("[PROMPT-MGR] Cannot activate unknown version: %s", version_id)
            return False

        pair = (pv.prompt_key, pv.model_tier)

        # Deactivate previous active version for this pair
        prev_id = self._active.get(pair)
        if prev_id and prev_id in self._versions:
            self._versions[prev_id].is_active = False
            self._update_active_in_db(prev_id, False)

        # Activate new version
        pv.is_active = True
        self._active[pair] = version_id
        self._update_active_in_db(version_id, True)

        logger.debug(
            "[PROMPT-MGR] Activated %s for %s/%s (prev=%s)",
            version_id,
            pv.prompt_key,
            pv.model_tier,
            prev_id,
        )
        return True

    def rollback(self, prompt_key: str, model_tier: str) -> PromptVersion | None:
        """Rollback to the parent version for a (prompt_key, model_tier) pair.

        Finds the currently active version, looks up its parent_version_id,
        and activates the parent.

        Args:
            prompt_key: Logical prompt name.
            model_tier: Target model tier.

        Returns:
            The newly active (parent) version, or None if no parent exists.
        """
        current = self.get_active(prompt_key, model_tier)
        if current is None:
            logger.debug(
                "[PROMPT-MGR] No active version to rollback for %s/%s", prompt_key, model_tier
            )
            return None

        parent_id = current.parent_version_id
        if parent_id is None or parent_id not in self._versions:
            logger.debug(
                "[PROMPT-MGR] No parent version for rollback: %s/%s (current=%s)",
                prompt_key,
                model_tier,
                current.version_id,
            )
            return None

        self.activate(parent_id)
        return self._versions[parent_id]

    def get_active(self, prompt_key: str, model_tier: str) -> PromptVersion | None:
        """Get the currently active version for a (prompt_key, model_tier) pair.

        Args:
            prompt_key: Logical prompt name.
            model_tier: Target model tier.

        Returns:
            The active PromptVersion, or None if none is active.
        """
        version_id = self._active.get((prompt_key, model_tier))
        if version_id is None:
            return None
        return self._versions.get(version_id)

    def get_history(
        self,
        prompt_key: str,
        model_tier: str | None = None,
        limit: int = 20,
    ) -> list[PromptVersion]:
        """Get version history for a prompt key.

        Args:
            prompt_key: Logical prompt name.
            model_tier: Optional tier filter.
            limit: Maximum number of versions to return.

        Returns:
            List of PromptVersion sorted by created_at desc.
        """
        matches = [
            pv
            for pv in self._versions.values()
            if pv.prompt_key == prompt_key and (model_tier is None or pv.model_tier == model_tier)
        ]
        matches.sort(key=lambda pv: pv.created_at, reverse=True)
        return matches[:limit]

    def _persist_version(self, version: PromptVersion) -> None:
        """Persist a prompt version to DB.

        Best-effort: failures are logged but never raised.
        """
        try:
            from core.database.models import PromptVersionRecord
            from core.database.session import get_session

            with get_session() as session:
                rec = PromptVersionRecord(
                    version_id=version.version_id,
                    prompt_key=version.prompt_key,
                    model_tier=version.model_tier,
                    content=version.content,
                    is_active=version.is_active,
                    created_at=version.created_at,
                    created_by=version.created_by,
                    optimization_cycle_id=version.optimization_cycle_id,
                    parent_version_id=version.parent_version_id,
                    metrics_snapshot=version.metrics_snapshot,
                )
                session.add(rec)
                session.commit()
        except Exception:
            logger.debug(
                "[PROMPT-MGR] Failed to persist version %s to DB",
                version.version_id,
                exc_info=True,
            )

    def _update_active_in_db(self, version_id: str, is_active: bool) -> None:
        """Update the is_active flag for a version in DB.

        Best-effort: failures are logged but never raised.
        """
        try:
            from core.database.models import PromptVersionRecord
            from core.database.session import get_session

            with get_session() as session:
                rec = session.query(PromptVersionRecord).filter_by(version_id=version_id).first()
                if rec:
                    rec.is_active = is_active
                    session.commit()
        except Exception:
            logger.debug(
                "[PROMPT-MGR] Failed to update active flag for %s in DB",
                version_id,
                exc_info=True,
            )

# ---- Singleton with double-checked locking ----------------------------------------

_prompt_manager: PromptVersionManager | None = None
_prompt_manager_lock = threading.Lock()

def get_prompt_manager() -> PromptVersionManager:
    """Get or create the singleton PromptVersionManager instance."""
    global _prompt_manager
    if _prompt_manager is None:
        with _prompt_manager_lock:
            if _prompt_manager is None:
                _prompt_manager = PromptVersionManager()
    return _prompt_manager
