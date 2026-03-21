"""SQLAlchemy ORM-backed artifact registry for the Agent Factory.

Factory artifacts, versions, signals, escalation history, and suggestion
logs share the main PostgreSQL database engine.
"""

import json
import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from core.factory.models import (
    ArtifactStatus,
    ArtifactType,
    ArtifactVersion,
    FactoryArtifact,
    RelevanceSignal,
)

logger = logging.getLogger(__name__)

__all__ = ["FactoryRegistry", "get_factory_registry", "register_a2a_agent"]

# ---------------------------------------------------------------------------
# JSON serialization helpers (kept for ORM Text columns)
# ---------------------------------------------------------------------------

def _serialize_json(value: Any) -> str:
    """Convert dict/list to JSON string for TEXT columns."""
    if value is None:
        return "{}"
    return json.dumps(value)

def _deserialize_json(text: str | None) -> Any:
    """Parse JSON string back to dict/list, with safe fallback."""
    if not text:
        return {}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}

# ---------------------------------------------------------------------------
# FactoryRegistry
# ---------------------------------------------------------------------------

class FactoryRegistry:
    """SQLAlchemy ORM-backed registry for factory artifacts, versions, and signals.

    Uses the shared database engine via ``get_session()`` from
    ``core.database.session``.  No separate database file is created.
    """

    def __init__(self, **kwargs: Any):
        """Initialize the registry.

        Args:
            **kwargs: Ignored (backward compat shim for old db_path parameter).
        """
        pass  # No initialization needed -- sessions come from get_session()

    # -- Lazy imports to avoid circular dependency at module level -----------

    @staticmethod
    def _get_session():
        """Return the ``get_session()`` context manager (lazy import)."""
        from core.database.session import get_session

        return get_session()

    @staticmethod
    def _models():
        """Return model classes (lazy import)."""
        from core.database.models import (
            ArtifactVersionRecord,
            EscalationHistoryRecord,
            FactoryArtifactRecord,
            RelevanceSignalRecord,
            SuggestionLogRecord,
        )

        return (
            FactoryArtifactRecord,
            ArtifactVersionRecord,
            RelevanceSignalRecord,
            EscalationHistoryRecord,
            SuggestionLogRecord,
        )

    # -- CRUD: register / get / list / update / archive / delete -------------

    def register(self, artifact: FactoryArtifact) -> str:
        """Insert a new artifact and create its initial version entry.

        Args:
            artifact: The FactoryArtifact to persist.

        Returns:
            The artifact id.

        Raises:
            ValueError: If an artifact with the same name already exists.
        """
        (
            FactoryArtifactRecord,
            ArtifactVersionRecord,
            _,
            _,
            _,
        ) = self._models()
        now = datetime.now(UTC).isoformat()

        with self._get_session() as session:
            existing = session.query(FactoryArtifactRecord).filter_by(name=artifact.name).first()
            if existing:
                raise ValueError(
                    f"Artifact '{artifact.name}' already exists (id={existing.id}). "
                    "Use a different name or update the existing artifact."
                )
            record = FactoryArtifactRecord(
                id=artifact.id,
                name=artifact.name,
                artifact_type=artifact.artifact_type.value,
                framework=artifact.framework,
                version=artifact.version,
                status=artifact.status.value,
                source_prompt=artifact.source_prompt,
                config_json=_serialize_json(artifact.config_json),
                artifact_path=artifact.artifact_path,
                test_result=artifact.test_result,
                test_passed=int(artifact.test_passed),
                test_iterations=artifact.test_iterations,
                trigger=artifact.trigger,
                tags=_serialize_json(artifact.tags),
                created_at=artifact.created_at.isoformat(),
                updated_at=artifact.updated_at.isoformat(),
                created_by=artifact.created_by,
            )
            session.add(record)
            session.flush()  # Ensure parent row exists before FK child

            # Create initial version entry
            version_record = ArtifactVersionRecord(
                id=str(uuid4()),
                artifact_id=artifact.id,
                version=1,
                config_json=_serialize_json(artifact.config_json),
                files_snapshot=_serialize_json([]),
                created_at=now,
                rollback_reason=None,
            )
            session.add(version_record)

        logger.info("Registered artifact: %s (id=%s)", artifact.name, artifact.id)
        return artifact.id

    def get(self, name: str) -> FactoryArtifact | None:
        """Look up an artifact by name.

        Args:
            name: The unique artifact name.

        Returns:
            FactoryArtifact if found, None otherwise.
        """
        FactoryArtifactRecord = self._models()[0]

        with self._get_session() as session:
            record = (
                session.query(FactoryArtifactRecord)
                .filter(FactoryArtifactRecord.name == name)
                .first()
            )
            if record is None:
                return None
            return self._record_to_artifact(record)

    def get_by_id(self, artifact_id: str) -> FactoryArtifact | None:
        """Look up an artifact by its unique identifier.

        Args:
            artifact_id: The UUID-style artifact id.

        Returns:
            FactoryArtifact if found, None otherwise.
        """
        FactoryArtifactRecord = self._models()[0]

        with self._get_session() as session:
            record = session.get(FactoryArtifactRecord, artifact_id)
            if record is None:
                return None
            return self._record_to_artifact(record)

    def list_all(
        self,
        artifact_type: ArtifactType | None = None,
        status: ArtifactStatus | None = None,
    ) -> list[FactoryArtifact]:
        """List artifacts with optional filters.

        Args:
            artifact_type: Filter by artifact type (agent/tool/skill).
            status: Filter by lifecycle status.

        Returns:
            List of matching FactoryArtifact objects.
        """
        FactoryArtifactRecord = self._models()[0]

        with self._get_session() as session:
            query = session.query(FactoryArtifactRecord)
            if artifact_type is not None:
                query = query.filter(FactoryArtifactRecord.artifact_type == artifact_type.value)
            if status is not None:
                query = query.filter(FactoryArtifactRecord.status == status.value)
            query = query.order_by(FactoryArtifactRecord.created_at.desc())
            rows = query.all()
            return [self._record_to_artifact(r) for r in rows]

    def update_status(self, name: str, status: ArtifactStatus) -> None:
        """Update the lifecycle status of an artifact.

        Args:
            name: Artifact name.
            status: New status value.
        """
        FactoryArtifactRecord = self._models()[0]
        now = datetime.now(UTC).isoformat()

        with self._get_session() as session:
            record = (
                session.query(FactoryArtifactRecord)
                .filter(FactoryArtifactRecord.name == name)
                .first()
            )
            if record:
                record.status = status.value
                record.updated_at = now

    def update_artifact(self, name: str, **fields: Any) -> None:
        """Update specific fields on an artifact.

        Only the following fields may be updated: status, test_result,
        test_passed, test_iterations, config_json, tags, artifact_path,
        version.

        Args:
            name: Artifact name.
            **fields: Keyword arguments for allowed field names.

        Raises:
            ValueError: If a disallowed field name is provided.
        """
        allowed = {
            "status",
            "test_result",
            "test_passed",
            "test_iterations",
            "config_json",
            "tags",
            "artifact_path",
            "version",
        }
        invalid = set(fields.keys()) - allowed
        if invalid:
            raise ValueError(f"Cannot update fields: {sorted(invalid)}")

        if not fields:
            return

        FactoryArtifactRecord = self._models()[0]
        now = datetime.now(UTC).isoformat()

        with self._get_session() as session:
            record = (
                session.query(FactoryArtifactRecord)
                .filter(FactoryArtifactRecord.name == name)
                .first()
            )
            if record is None:
                return

            for key, value in fields.items():
                if key in ("config_json", "tags"):
                    value = _serialize_json(value)
                elif key == "test_passed":
                    value = int(value)
                elif key == "status" and isinstance(value, ArtifactStatus):
                    value = value.value
                setattr(record, key, value)

            record.updated_at = now

    def add_version(
        self,
        artifact_id: str,
        version: int,
        config_json: dict,
        files: list[str],
        rollback_reason: str | None = None,
    ) -> str:
        """Add a new version entry for an artifact.

        Args:
            artifact_id: Parent artifact identifier.
            version: Version number (must be unique per artifact).
            config_json: Configuration snapshot at this version.
            files: List of file paths in this version.
            rollback_reason: Optional reason if this is a rollback target.

        Returns:
            The generated version entry id.
        """
        ArtifactVersionRecord = self._models()[1]
        version_id = str(uuid4())
        now = datetime.now(UTC).isoformat()

        with self._get_session() as session:
            record = ArtifactVersionRecord(
                id=version_id,
                artifact_id=artifact_id,
                version=version,
                config_json=_serialize_json(config_json),
                files_snapshot=_serialize_json(files),
                created_at=now,
                rollback_reason=rollback_reason,
            )
            session.add(record)

        return version_id

    def get_versions(self, artifact_id: str) -> list[ArtifactVersion]:
        """Get all version entries for an artifact, ordered by version.

        Args:
            artifact_id: Parent artifact identifier.

        Returns:
            List of ArtifactVersion objects in ascending version order.
        """
        ArtifactVersionRecord = self._models()[1]

        with self._get_session() as session:
            rows = (
                session.query(ArtifactVersionRecord)
                .filter(ArtifactVersionRecord.artifact_id == artifact_id)
                .order_by(ArtifactVersionRecord.version)
                .all()
            )
            return [self._version_record_to_model(r) for r in rows]

    def archive(self, name: str) -> bool:
        """Soft-delete an artifact by setting status to ARCHIVED.

        Args:
            name: Artifact name.

        Returns:
            True if the artifact was archived, False if not found or
            already archived.
        """
        FactoryArtifactRecord = self._models()[0]
        now = datetime.now(UTC).isoformat()

        with self._get_session() as session:
            record = (
                session.query(FactoryArtifactRecord)
                .filter(
                    FactoryArtifactRecord.name == name,
                    FactoryArtifactRecord.status != "archived",
                )
                .first()
            )
            if record is None:
                return False
            record.status = "archived"
            record.updated_at = now
            return True

    def hard_delete(self, name: str) -> bool:
        """Permanently delete an artifact and its version history.

        Cascading delete on artifact_versions is handled by the FK constraint.

        Args:
            name: Artifact name.

        Returns:
            True if the artifact was deleted, False if not found.
        """
        FactoryArtifactRecord = self._models()[0]

        with self._get_session() as session:
            record = (
                session.query(FactoryArtifactRecord)
                .filter(FactoryArtifactRecord.name == name)
                .first()
            )
            if record is None:
                return False
            session.delete(record)
            return True

    # -- Record conversion helpers -------------------------------------------

    @staticmethod
    def _record_to_artifact(record) -> FactoryArtifact:
        """Convert a FactoryArtifactRecord ORM object to FactoryArtifact."""
        return FactoryArtifact(
            id=record.id,
            name=record.name,
            artifact_type=ArtifactType(record.artifact_type),
            framework=record.framework,
            version=record.version,
            status=ArtifactStatus(record.status),
            source_prompt=record.source_prompt,
            config_json=_deserialize_json(record.config_json),
            artifact_path=record.artifact_path,
            test_result=record.test_result,
            test_passed=bool(record.test_passed),
            test_iterations=record.test_iterations,
            trigger=record.trigger,
            tags=_deserialize_json(record.tags),
            created_at=datetime.fromisoformat(record.created_at),
            updated_at=datetime.fromisoformat(record.updated_at),
            created_by=record.created_by,
        )

    @staticmethod
    def _version_record_to_model(record) -> ArtifactVersion:
        """Convert an ArtifactVersionRecord ORM object to ArtifactVersion."""
        return ArtifactVersion(
            id=record.id,
            artifact_id=record.artifact_id,
            version=record.version,
            config_json=_deserialize_json(record.config_json),
            files_snapshot=_deserialize_json(record.files_snapshot),
            created_at=datetime.fromisoformat(record.created_at),
            rollback_reason=record.rollback_reason,
        )

    # -- Relevance signals CRUD -----------------------------------------------

    def upsert_signal(self, signal: RelevanceSignal) -> str:
        """Insert or update a relevance signal by (signal_type, pattern) key.

        Args:
            signal: The RelevanceSignal to persist.

        Returns:
            The signal id.
        """
        RelevanceSignalRecord = self._models()[2]
        now = datetime.now(UTC)

        with self._get_session() as session:
            existing = (
                session.query(RelevanceSignalRecord)
                .filter(
                    RelevanceSignalRecord.signal_type == signal.signal_type,
                    RelevanceSignalRecord.pattern == signal.pattern,
                )
                .first()
            )

            signal_id = existing.id if existing else str(uuid4())

            if existing:
                # Update in place
                existing.count = signal.count
                existing.confidence = signal.confidence
                existing.example_queries = _serialize_json(signal.example_queries)
                existing.suggested_type = (
                    signal.suggested_type.value if signal.suggested_type else None
                )
                existing.urgency = signal.urgency
                existing.last_seen = (signal.last_seen or now).isoformat()
                existing.status = "open"
                existing.resolved_artifact_id = None
            else:
                record = RelevanceSignalRecord(
                    id=signal_id,
                    signal_type=signal.signal_type,
                    pattern=signal.pattern,
                    count=signal.count,
                    confidence=signal.confidence,
                    example_queries=_serialize_json(signal.example_queries),
                    suggested_type=(signal.suggested_type.value if signal.suggested_type else None),
                    urgency=signal.urgency,
                    first_seen=(signal.first_seen or now).isoformat(),
                    last_seen=(signal.last_seen or now).isoformat(),
                    status="open",
                    resolved_artifact_id=None,
                )
                session.add(record)

        return signal_id

    def get_signals(
        self,
        signal_type: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        """Query relevance signals with optional filters.

        Args:
            signal_type: Filter by signal type.
            status: Filter by status (e.g. 'open', 'resolved').

        Returns:
            List of dicts with all signal columns.
        """
        RelevanceSignalRecord = self._models()[2]

        with self._get_session() as session:
            query = session.query(RelevanceSignalRecord)
            if signal_type is not None:
                query = query.filter(RelevanceSignalRecord.signal_type == signal_type)
            if status is not None:
                query = query.filter(RelevanceSignalRecord.status == status)
            query = query.order_by(RelevanceSignalRecord.last_seen.desc())

            rows = query.all()
            results: list[dict] = []
            for row in rows:
                d = {
                    "id": row.id,
                    "signal_type": row.signal_type,
                    "pattern": row.pattern,
                    "count": row.count,
                    "confidence": row.confidence,
                    "example_queries": _deserialize_json(row.example_queries),
                    "suggested_type": row.suggested_type,
                    "urgency": row.urgency,
                    "first_seen": row.first_seen,
                    "last_seen": row.last_seen,
                    "status": row.status,
                    "resolved_artifact_id": row.resolved_artifact_id,
                }
                results.append(d)
            return results

    def resolve_signal(self, signal_id: str, artifact_id: str) -> None:
        """Mark a signal as resolved by linking it to an artifact.

        Args:
            signal_id: The signal to resolve.
            artifact_id: The artifact that resolved this signal.
        """
        RelevanceSignalRecord = self._models()[2]

        with self._get_session() as session:
            record = session.get(RelevanceSignalRecord, signal_id)
            if record:
                record.status = "resolved"
                record.resolved_artifact_id = artifact_id

    def list_open_signals(self) -> list[dict]:
        """Convenience method to list all open (unresolved) signals.

        Returns:
            List of dicts for signals with status='open'.
        """
        return self.get_signals(status="open")

    # -- Escalation history CRUD ----------------------------------------------

    def record_escalation(
        self,
        action_type: str,
        description: str,
        conversation_id: str,
        suggested_name: str = "",
    ) -> str:
        """Record an escalation event in the history table.

        Args:
            action_type: The escalation action type value.
            description: Human-readable description of the escalation.
            conversation_id: The conversation that triggered the escalation.
            suggested_name: Optional suggested artifact name.

        Returns:
            The generated escalation id.
        """
        EscalationHistoryRecord = self._models()[3]
        esc_id = str(uuid4())
        now = datetime.now(UTC).isoformat()

        with self._get_session() as session:
            record = EscalationHistoryRecord(
                id=esc_id,
                action_type=action_type,
                description=description,
                conversation_id=conversation_id,
                suggested_name=suggested_name,
                status="pending",
                created_at=now,
            )
            session.add(record)

        return esc_id

    def get_escalation_history(self, since_hours: int = 72) -> list[dict]:
        """Get recent escalation history.

        Args:
            since_hours: Look back this many hours (default 72).

        Returns:
            List of dicts with all escalation_history columns.
        """
        EscalationHistoryRecord = self._models()[3]
        cutoff = (datetime.now(UTC) - timedelta(hours=since_hours)).isoformat()

        with self._get_session() as session:
            rows = (
                session.query(EscalationHistoryRecord)
                .filter(EscalationHistoryRecord.created_at >= cutoff)
                .order_by(EscalationHistoryRecord.created_at.desc())
                .all()
            )
            return [
                {
                    "id": r.id,
                    "action_type": r.action_type,
                    "description": r.description,
                    "conversation_id": r.conversation_id,
                    "suggested_name": r.suggested_name,
                    "status": r.status,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    def update_escalation_status(self, conversation_id: str, status: str) -> None:
        """Update the status of pending escalations for a conversation.

        Args:
            conversation_id: The conversation whose escalations to update.
            status: New status value (e.g. 'resolved', 'rejected').
        """
        EscalationHistoryRecord = self._models()[3]

        with self._get_session() as session:
            records = (
                session.query(EscalationHistoryRecord)
                .filter(
                    EscalationHistoryRecord.conversation_id == conversation_id,
                    EscalationHistoryRecord.status == "pending",
                )
                .all()
            )
            for record in records:
                record.status = status

    # -- Suggestion log CRUD (rate limiting) ----------------------------------

    def record_suggestion(
        self,
        category: str,
        status: str,
        session_id: str = "",
    ) -> str:
        """Record a proactive suggestion event.

        Args:
            category: Suggestion category (e.g. 'routing_gap').
            status: Status of the suggestion (e.g. 'pending', 'accepted', 'rejected').
            session_id: Optional session identifier.

        Returns:
            The generated suggestion id.
        """
        SuggestionLogRecord = self._models()[4]
        sug_id = str(uuid4())
        now = datetime.now(UTC).isoformat()

        with self._get_session() as session:
            record = SuggestionLogRecord(
                id=sug_id,
                category=category,
                status=status,
                session_id=session_id,
                created_at=now,
            )
            session.add(record)

        return sug_id

    def count_suggestions(
        self,
        session_id: str | None = None,
        category: str | None = None,
        since_hours: int | None = None,
    ) -> int:
        """Count suggestion log entries with optional filters.

        Args:
            session_id: Filter by session.
            category: Filter by category.
            since_hours: Only count entries within this many hours.

        Returns:
            Integer count of matching entries.
        """
        SuggestionLogRecord = self._models()[4]

        with self._get_session() as session:
            from sqlalchemy import func

            query = session.query(func.count(SuggestionLogRecord.id))

            if session_id is not None:
                query = query.filter(SuggestionLogRecord.session_id == session_id)
            if category is not None:
                query = query.filter(SuggestionLogRecord.category == category)
            if since_hours is not None:
                cutoff = (datetime.now(UTC) - timedelta(hours=since_hours)).isoformat()
                query = query.filter(SuggestionLogRecord.created_at >= cutoff)

            return query.scalar() or 0

    def last_rejection(self, category: str) -> datetime | None:
        """Get the timestamp of the most recent rejection for a category.

        Args:
            category: The suggestion category to check.

        Returns:
            datetime of last rejection, or None if no rejections found.
        """
        SuggestionLogRecord = self._models()[4]

        with self._get_session() as session:
            from sqlalchemy import func

            val = (
                session.query(func.max(SuggestionLogRecord.created_at))
                .filter(
                    SuggestionLogRecord.category == category,
                    SuggestionLogRecord.status == "rejected",
                )
                .scalar()
            )
            if val:
                return datetime.fromisoformat(val)
            return None

    def last_artifact_creation(self) -> datetime | None:
        """Get the timestamp of the most recent non-archived artifact creation.

        Returns:
            datetime of last artifact creation, or None if no artifacts exist.
        """
        FactoryArtifactRecord = self._models()[0]

        with self._get_session() as session:
            from sqlalchemy import func

            val = (
                session.query(func.max(FactoryArtifactRecord.created_at))
                .filter(FactoryArtifactRecord.status != "archived")
                .scalar()
            )
            if val:
                return datetime.fromisoformat(val)
            return None

# ---------------------------------------------------------------------------
# Module-level singleton (double-checked locking)
# ---------------------------------------------------------------------------

_registry: FactoryRegistry | None = None
_registry_lock = threading.Lock()

def get_factory_registry() -> FactoryRegistry:
    """Get or create the global FactoryRegistry singleton.

    Uses double-checked locking to avoid lock acquisition on every call
    while ensuring thread-safe singleton creation.
    """
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = FactoryRegistry()
    return _registry

# ---------------------------------------------------------------------------
# A2A agent registration (module-level async function)
# ---------------------------------------------------------------------------

async def register_a2a_agent(
    endpoint: str,
    name: str | None = None,
    auth_token: str | None = None,
    api_key: str | None = None,
) -> FactoryArtifact:
    """Register a remote A2A-compliant agent as a factory artifact.

    This implements Track 2 Item 20 from the implementation spec: registering
    remote A2A endpoints as factory artifacts. A2A agents skip the scaffold and
    test phases since they are already running remotely.

    Args:
        endpoint: Base URL of the A2A-compliant agent.
        name: Optional override name (defaults to agent card name).
        auth_token: Optional Bearer token for the remote agent.
        api_key: Optional API key for the remote agent.

    Returns:
        The created FactoryArtifact with status=ACTIVE and framework='a2a'.
    """
    # Lazy imports to avoid circular dependencies
    from core.adapters.a2a_adapter import A2AAgentAdapter
    from core.adapters.registry import get_registry

    # Create adapter and validate the endpoint is live
    adapter = A2AAgentAdapter(endpoint=endpoint, auth_token=auth_token, api_key=api_key)
    card = await adapter._fetch_card()

    agent_name = name or card.name

    # Register in the runtime AgentRegistry for discovery
    get_registry().register(adapter)

    # Create factory artifact record
    now = datetime.now(UTC)
    artifact = FactoryArtifact(
        id=str(uuid4()),
        name=agent_name,
        artifact_type=ArtifactType.AGENT,
        framework="a2a",
        status=ArtifactStatus.ACTIVE,
        source_prompt=f"A2A remote agent at {endpoint}",
        config_json={"endpoint": endpoint, "a2a_enabled": True},
        artifact_path=endpoint,
        created_by="factory",
        trigger="user",
        created_at=now,
        updated_at=now,
    )

    # Persist in the factory registry
    get_factory_registry().register(artifact)

    logger.info("Registered A2A agent: %s at %s", agent_name, endpoint)
    return artifact
