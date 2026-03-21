"""Audit trail observer for the ChatEvent stream.

Captures tool calls, agent dispatches, LLM decisions, and completions
from the unified event protocol and persists them to audit_logs.
"""

import logging
from typing import Any

from core.extensions.events import ChatEvent

logger = logging.getLogger(__name__)

# Event types that generate audit entries
_TRACED_EVENTS = {
    "tool_start", "tool_result",
    "agent_start", "agent_complete",
    "complete", "error",
    "escalation", "approval_pending", "approval_resolved",
    "thinking", "reasoning",
    "flow_start", "flow_complete",
    "node_start", "node_complete",
    "failover",
}

class AuditTracer:
    """Observes ChatEvent stream and collects audit entries.

    Usage:
        tracer = AuditTracer(user_id=uid, conversation_id=cid)
        for event in orchestrator_events:
            tracer.observe(event)
            yield event  # pass through
        tracer.persist()  # write all entries to DB
    """

    def __init__(
        self,
        user_id: str | None = None,
        conversation_id: str | None = None,
        mode: str | None = None,
    ):
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.mode = mode
        self.entries: list[dict[str, Any]] = []

    def observe(self, event: ChatEvent) -> None:
        """Process a ChatEvent and create audit entry if traceable."""
        if event.type not in _TRACED_EVENTS:
            return

        entry = {
            "action": self._map_action(event),
            "resource_type": "orchestration",
            "resource_id": self.conversation_id,
            "metadata": self._extract_metadata(event),
        }
        self.entries.append(entry)

    def _map_action(self, event: ChatEvent) -> str:
        """Map ChatEvent type to audit action name."""
        mapping = {
            "complete": "chat_complete",
            "error": "chat_error",
            "thinking": "llm_thinking",
            "reasoning": "llm_reasoning",
        }
        return mapping.get(event.type, event.type)

    def _extract_metadata(self, event: ChatEvent) -> dict[str, Any]:
        """Extract relevant metadata from event for audit trail."""
        meta = dict(event.metadata) if event.metadata else {}
        meta["event_type"] = event.type
        meta["timestamp"] = event.timestamp

        if event.type == "tool_start":
            meta["tool_name"] = meta.get("tool", "")
            meta["arguments"] = meta.get("arguments", {})
        elif event.type == "tool_result":
            meta["tool_name"] = meta.get("tool", "")
            meta["success"] = meta.get("success", True)
            meta["duration_ms"] = meta.get("duration_ms", 0)
            if event.content and len(event.content) > 500:
                meta["result_preview"] = event.content[:500]
        elif event.type == "agent_start":
            meta["agent_name"] = meta.get("agent", "")
        elif event.type == "agent_complete":
            meta["agent_name"] = meta.get("agent", "")
            meta["duration_ms"] = meta.get("duration_ms", 0)
        elif event.type == "error":
            meta["error_code"] = meta.get("code") or meta.get("error_code", "UNKNOWN")
            meta["error_message"] = event.content
        elif event.type == "complete":
            meta["mode"] = meta.get("mode", self.mode)
            meta["response_length"] = len(event.content) if event.content else 0
        elif event.type == "escalation":
            meta["escalation_type"] = meta.get("action_type", "")
        elif event.type == "failover":
            meta["from_provider"] = meta.get("from_provider", "")
            meta["to_provider"] = meta.get("to_provider", "")

        return meta

    def persist(self) -> None:
        """Write all collected entries to audit_logs table."""
        if not self.entries:
            return

        from core.auth.audit import log_audit_sync

        for entry in self.entries:
            try:
                log_audit_sync(
                    db=None,
                    user_id=self.user_id or "",
                    action=entry["action"],
                    resource_type=entry.get("resource_type", "orchestration"),
                    resource_id=entry.get("resource_id"),
                    metadata=entry.get("metadata"),
                    event_severity="info",
                )
            except Exception:
                logger.warning(
                    f"Failed to persist audit entry: {entry.get('action')}",
                    exc_info=True,
                )

    def add_custom(self, action: str, metadata: dict[str, Any] | None = None) -> None:
        """Add a custom audit entry (for events outside ChatEvent stream)."""
        self.entries.append({
            "action": action,
            "resource_type": "orchestration",
            "resource_id": self.conversation_id,
            "metadata": metadata or {},
        })

