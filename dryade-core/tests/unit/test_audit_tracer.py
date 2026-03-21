"""Tests for AuditTracer — ChatEvent stream observer."""

from unittest.mock import patch

from core.audit.tracer import AuditTracer
from core.extensions.events import (
    emit_agent_complete,
    emit_agent_start,
    emit_complete,
    emit_error,
    emit_tool_result,
    emit_tool_start,
)

def test_tracer_tracks_tool_call():
    tracer = AuditTracer(user_id="u1", conversation_id="c1")
    tracer.observe(emit_tool_start("list_directory", {"path": "/tmp"}))
    tracer.observe(emit_tool_result("list_directory", "file1\nfile2", 15.0, success=True))
    assert len(tracer.entries) == 2
    assert tracer.entries[0]["action"] == "tool_start"
    assert tracer.entries[1]["action"] == "tool_result"
    assert tracer.entries[1]["metadata"]["success"] is True

def test_tracer_tracks_agent_dispatch():
    tracer = AuditTracer(user_id="u1", conversation_id="c1")
    tracer.observe(emit_agent_start("mcp-filesystem", "List files"))
    tracer.observe(emit_agent_complete("mcp-filesystem", "file1", 200.0))
    assert len(tracer.entries) == 2
    assert tracer.entries[0]["action"] == "agent_start"
    assert tracer.entries[1]["action"] == "agent_complete"

def test_tracer_tracks_completion():
    tracer = AuditTracer(user_id="u1", conversation_id="c1")
    tracer.observe(emit_complete(response="Hello", mode="chat"))
    assert len(tracer.entries) == 1
    assert tracer.entries[0]["action"] == "chat_complete"

def test_tracer_tracks_error():
    tracer = AuditTracer(user_id="u1", conversation_id="c1")
    tracer.observe(emit_error("Something failed", "INTERNAL"))
    assert len(tracer.entries) == 1
    assert tracer.entries[0]["metadata"]["error_code"] == "INTERNAL"

def test_tracer_ignores_non_traced_events():
    from core.extensions.events import emit_token

    tracer = AuditTracer(user_id="u1", conversation_id="c1")
    tracer.observe(emit_token("hello"))
    assert len(tracer.entries) == 0

def test_tracer_add_custom():
    tracer = AuditTracer(user_id="u1", conversation_id="c1")
    tracer.add_custom("chat_request", {"message_length": 42, "mode": "chat"})
    assert len(tracer.entries) == 1
    assert tracer.entries[0]["action"] == "chat_request"
    assert tracer.entries[0]["metadata"]["message_length"] == 42

@patch("core.auth.audit.log_audit_sync")
def test_tracer_persist_writes_to_db(mock_log):
    tracer = AuditTracer(user_id="u1", conversation_id="c1")
    tracer.observe(emit_tool_start("read_file", {"path": "/tmp/x"}))
    tracer.observe(emit_tool_result("read_file", "content", 10.0))
    tracer.persist()
    assert mock_log.call_count == 2

@patch("core.auth.audit.log_audit_sync", side_effect=Exception("DB down"))
def test_tracer_persist_handles_errors_gracefully(mock_log):
    tracer = AuditTracer(user_id="u1", conversation_id="c1")
    tracer.observe(emit_tool_start("read_file", {"path": "/tmp/x"}))
    tracer.persist()  # Should not raise
    assert mock_log.call_count == 1
