# Migrated from tests/unit/plugins/test_safety.py -- imports updated to core.safety.validator (Phase 222).

"""
Unit tests for safety validator (core module).

Tests cover:
1. Safety classification (SAFE, APPROVE, UNSAFE)
2. Input validation (Pydantic models)
3. Output sanitization (HTML, SQL, Shell, JSON)
4. Context detection
5. Convenience functions
6. ValidationResult model
"""

import pytest

from core.safety.validator import (
    ChatMessage,
    FileUpload,
    InputValidator,
    OutputSanitizer,
    SafetyClassifier,
    SafetyLevel,
    SanitizationContext,
    ToolArgs,
    ValidationResult,
    classify_safety,
    is_blocked_operation,
    is_safe_operation,
    sanitize_output,
    validate_input,
)

@pytest.mark.unit
class TestSafetyClassifier:
    """Tests for SafetyClassifier."""

    def test_classify_unsafe_rm_rf(self):
        """Test rm -rf / is classified as UNSAFE."""
        level, reason = classify_safety("bash", {"command": "rm -rf /"})
        assert level == SafetyLevel.UNSAFE

    def test_classify_unsafe_rm_rf_wildcard(self):
        """Test rm -rf /* is classified as UNSAFE."""
        level, reason = classify_safety("bash", {"command": "rm -rf /*"})
        assert level == SafetyLevel.UNSAFE

    def test_classify_unsafe_fork_bomb(self):
        """Test fork bomb is classified as UNSAFE."""
        level, reason = classify_safety("bash", {"command": ":(){ :|:& };:"})
        assert level == SafetyLevel.UNSAFE

    def test_classify_unsafe_dd_disk_write(self):
        """Test dd to disk device is UNSAFE."""
        level, reason = classify_safety("bash", {"command": "dd if=/dev/zero of=/dev/sda"})
        assert level == SafetyLevel.UNSAFE

    def test_classify_unsafe_mkfs(self):
        """Test mkfs is classified as UNSAFE."""
        level, reason = classify_safety("bash", {"command": "mkfs.ext4 /dev/sda1"})
        assert level == SafetyLevel.UNSAFE

    def test_classify_approve_pip_install(self):
        """Test pip install requires approval."""
        level, reason = classify_safety("bash", {"command": "pip install requests"})
        assert level == SafetyLevel.APPROVE

    def test_classify_approve_git_push(self):
        """Test git push requires approval."""
        level, reason = classify_safety("bash", {"command": "git push origin main"})
        assert level == SafetyLevel.APPROVE

    def test_classify_approve_drop_table(self):
        """Test DROP TABLE requires approval."""
        level, reason = classify_safety("bash", {"command": "DROP TABLE users"})
        assert level == SafetyLevel.APPROVE

    def test_classify_safe_ls(self):
        """Test ls is classified as SAFE."""
        level, reason = classify_safety("bash", {"command": "ls -la"})
        assert level == SafetyLevel.SAFE

    def test_classify_safe_git_status(self):
        """Test git status is classified as SAFE."""
        level, reason = classify_safety("bash", {"command": "git status"})
        assert level == SafetyLevel.SAFE

    def test_classify_safe_cat(self):
        """Test cat is classified as SAFE."""
        level, reason = classify_safety("bash", {"command": "cat file.txt"})
        assert level == SafetyLevel.SAFE

    def test_is_safe_operation(self):
        """Test is_safe_operation helper."""
        assert is_safe_operation("bash", {"command": "ls"}) is True
        assert is_safe_operation("bash", {"command": "pip install"}) is False

    def test_is_blocked_operation(self):
        """Test is_blocked_operation helper."""
        assert is_blocked_operation("bash", {"command": "rm -rf /"}) is True
        assert is_blocked_operation("bash", {"command": "ls"}) is False

    def test_classify_unknown_defaults_to_approve(self):
        """Test unknown commands default to APPROVE."""
        level, reason = classify_safety("bash", {"command": "some_unknown_command"})
        assert level == SafetyLevel.APPROVE

    def test_classifier_instance_with_custom_rules(self):
        """Test classifier with custom rules."""
        from core.safety.validator import SafetyRule

        custom_rules = [
            SafetyRule(
                pattern=r"^custom_cmd",
                level=SafetyLevel.UNSAFE,
                reason="Custom blocked",
                category="custom",
            ),
        ]
        classifier = SafetyClassifier(rules=custom_rules)
        level, reason = classifier.classify("bash", {"command": "custom_cmd --arg"})
        assert level == SafetyLevel.UNSAFE

@pytest.mark.unit
class TestInputValidator:
    """Tests for InputValidator."""

    def test_validate_chat_message_valid(self):
        """Test valid chat message validation."""
        result = validate_input({"role": "user", "content": "Hello"}, ChatMessage)
        assert result.valid is True
        assert result.sanitized_input["role"] == "user"

    def test_validate_chat_message_invalid_role(self):
        """Test invalid role is rejected."""
        result = validate_input({"role": "invalid", "content": "Hello"}, ChatMessage)
        assert result.valid is False
        assert len(result.errors) > 0

    def test_validate_chat_message_all_valid_roles(self):
        """Test all valid roles pass validation."""
        for role in ["system", "user", "assistant", "tool"]:
            result = validate_input({"role": role, "content": "Hello"}, ChatMessage)
            assert result.valid is True, f"Role '{role}' should be valid"

    def test_validate_tool_args_valid(self):
        """Test valid tool args validation."""
        result = validate_input({"tool_name": "test_tool", "args": {"key": "value"}}, ToolArgs)
        assert result.valid is True

    def test_validate_tool_args_invalid_name(self):
        """Test invalid tool name is rejected."""
        result = validate_input({"tool_name": "invalid tool!", "args": {}}, ToolArgs)
        assert result.valid is False

    def test_validate_file_upload_path_traversal(self):
        """Test path traversal in filename is rejected."""
        result = validate_input(
            {"filename": "../../../etc/passwd", "content_type": "text/plain", "size": 100},
            FileUpload,
        )
        assert result.valid is False

    def test_validation_result_model(self):
        """Test ValidationResult dataclass."""
        result = ValidationResult(valid=True)
        assert result.valid is True
        assert result.errors == []
        assert result.sanitized_input is None

        result2 = ValidationResult(valid=False, errors=["error1"])
        assert result2.valid is False
        assert result2.errors == ["error1"]

@pytest.mark.unit
class TestOutputSanitizer:
    """Tests for OutputSanitizer."""

    def test_sanitize_html_escapes_script_tags(self):
        """Test HTML sanitization escapes script tags (XSS prevention)."""
        output = sanitize_output("<script>alert('xss')</script>", SanitizationContext.HTML)
        assert "<script>" not in output
        assert "&lt;script&gt;" in output

    def test_sanitize_html_escapes_attributes(self):
        """Test HTML sanitization escapes quotes."""
        output = sanitize_output('<img onerror="alert(1)">', SanitizationContext.HTML)
        assert 'onerror="alert(1)"' not in output

    def test_sanitize_sql_filters_drop(self):
        """Test SQL keyword filtering for DROP."""
        output = sanitize_output("User: DROP TABLE users", SanitizationContext.SQL)
        assert "DROP " not in output.upper() or "[SQL_FILTERED]" in output

    def test_sanitize_shell_quotes_pipes(self):
        """Test shell sanitization quotes dangerous patterns."""
        output = sanitize_output("value | rm -rf /", SanitizationContext.SHELL)
        assert output.startswith("'") or "|" not in output

    def test_sanitize_json_valid(self):
        """Test valid JSON passthrough."""
        output = sanitize_output('{"key": "value"}', SanitizationContext.JSON)
        assert '"key"' in output
        assert '"value"' in output

    def test_sanitize_json_invalid(self):
        """Test invalid JSON is escaped as string."""
        output = sanitize_output("not valid json", SanitizationContext.JSON)
        assert output.startswith('"')

    def test_detect_html_context(self):
        """Test HTML context detection."""
        sanitizer = OutputSanitizer()
        assert sanitizer.detect_context("/chat/messages") == SanitizationContext.HTML

    def test_detect_json_context(self):
        """Test JSON context detection for API routes."""
        sanitizer = OutputSanitizer()
        assert sanitizer.detect_context("/api/agents") == SanitizationContext.JSON

    def test_detect_sql_context(self):
        """Test SQL context detection."""
        sanitizer = OutputSanitizer()
        assert sanitizer.detect_context("/query/results") == SanitizationContext.SQL

    def test_detect_shell_context(self):
        """Test shell context detection."""
        sanitizer = OutputSanitizer()
        assert sanitizer.detect_context("/execute/command") == SanitizationContext.SHELL

@pytest.mark.unit
class TestSafetyLevel:
    """Tests for SafetyLevel enum."""

    def test_safety_levels_values(self):
        """Test all safety levels exist with correct values."""
        assert SafetyLevel.SAFE == "safe"
        assert SafetyLevel.APPROVE == "approve"
        assert SafetyLevel.UNSAFE == "unsafe"
