"""
Unit tests for safety module (migrated from plugin to core in Phase 222).

Tests cover:
1. Input validation (Pydantic models)
2. Output sanitization (HTML, SQL, Shell, JSON)
3. Context detection
4. Safety classification (SAFE, APPROVE, UNSAFE)
"""

import pytest

@pytest.mark.unit
class TestSafetyClassifier:
    """Tests for SafetyClassifier."""

    def test_classify_unsafe_rm_rf(self):
        """Test rm -rf / is classified as UNSAFE."""
        from core.safety.validator import SafetyLevel, classify_safety

        level, reason = classify_safety("bash", {"command": "rm -rf /"})
        assert level == SafetyLevel.UNSAFE

    def test_classify_unsafe_fork_bomb(self):
        """Test fork bomb is classified as UNSAFE."""
        from core.safety.validator import SafetyLevel, classify_safety

        level, reason = classify_safety("bash", {"command": ":(){ :|:& };:"})
        assert level == SafetyLevel.UNSAFE

    def test_classify_approve_pip_install(self):
        """Test pip install requires approval."""
        from core.safety.validator import SafetyLevel, classify_safety

        level, reason = classify_safety("bash", {"command": "pip install requests"})
        assert level == SafetyLevel.APPROVE

    def test_classify_approve_git_push(self):
        """Test git push requires approval."""
        from core.safety.validator import SafetyLevel, classify_safety

        level, reason = classify_safety("bash", {"command": "git push origin main"})
        assert level == SafetyLevel.APPROVE

    def test_classify_safe_ls(self):
        """Test ls is classified as SAFE."""
        from core.safety.validator import SafetyLevel, classify_safety

        level, reason = classify_safety("bash", {"command": "ls -la"})
        assert level == SafetyLevel.SAFE

    def test_classify_safe_git_status(self):
        """Test git status is classified as SAFE."""
        from core.safety.validator import SafetyLevel, classify_safety

        level, reason = classify_safety("bash", {"command": "git status"})
        assert level == SafetyLevel.SAFE

    def test_is_safe_operation(self):
        """Test is_safe_operation helper."""
        from core.safety.validator import is_safe_operation

        assert is_safe_operation("bash", {"command": "ls"}) is True
        assert is_safe_operation("bash", {"command": "pip install"}) is False

    def test_is_blocked_operation(self):
        """Test is_blocked_operation helper."""
        from core.safety.validator import is_blocked_operation

        assert is_blocked_operation("bash", {"command": "rm -rf /"}) is True
        assert is_blocked_operation("bash", {"command": "ls"}) is False

@pytest.mark.unit
class TestInputValidator:
    """Tests for InputValidator."""

    def test_validate_chat_message_valid(self):
        """Test valid chat message validation."""
        from core.safety.validator import ChatMessage, validate_input

        result = validate_input({"role": "user", "content": "Hello"}, ChatMessage)

        assert result.valid is True
        assert result.sanitized_input["role"] == "user"

    def test_validate_chat_message_invalid_role(self):
        """Test invalid role is rejected."""
        from core.safety.validator import ChatMessage, validate_input

        result = validate_input({"role": "invalid", "content": "Hello"}, ChatMessage)

        assert result.valid is False
        assert len(result.errors) > 0

    def test_validate_tool_args_valid(self):
        """Test valid tool args validation."""
        from core.safety.validator import ToolArgs, validate_input

        result = validate_input({"tool_name": "test_tool", "args": {"key": "value"}}, ToolArgs)

        assert result.valid is True

    def test_validate_tool_args_invalid_name(self):
        """Test invalid tool name is rejected."""
        from core.safety.validator import ToolArgs, validate_input

        result = validate_input({"tool_name": "invalid tool!", "args": {}}, ToolArgs)

        assert result.valid is False

    def test_validate_file_upload_path_traversal(self):
        """Test path traversal in filename is rejected."""
        from core.safety.validator import FileUpload, validate_input

        result = validate_input(
            {"filename": "../../../etc/passwd", "content_type": "text/plain", "size": 100},
            FileUpload,
        )

        assert result.valid is False

@pytest.mark.unit
class TestOutputSanitizer:
    """Tests for OutputSanitizer."""

    def test_sanitize_html(self):
        """Test HTML sanitization."""
        from core.safety.validator import SanitizationContext, sanitize_output

        output = sanitize_output("<script>alert('xss')</script>", SanitizationContext.HTML)

        assert "<script>" not in output
        assert "&lt;script&gt;" in output

    def test_sanitize_sql(self):
        """Test SQL keyword filtering."""
        from core.safety.validator import SanitizationContext, sanitize_output

        output = sanitize_output("User: DROP TABLE users", SanitizationContext.SQL)

        assert "DROP " not in output.upper() or "[SQL_FILTERED]" in output

    def test_sanitize_shell(self):
        """Test shell command sanitization."""
        from core.safety.validator import SanitizationContext, sanitize_output

        output = sanitize_output("value | rm -rf /", SanitizationContext.SHELL)

        # Should be quoted to prevent execution
        assert output.startswith("'") or "|" not in output

    def test_sanitize_json_valid(self):
        """Test valid JSON passthrough."""
        from core.safety.validator import SanitizationContext, sanitize_output

        output = sanitize_output('{"key": "value"}', SanitizationContext.JSON)

        assert '"key"' in output
        assert '"value"' in output

    def test_sanitize_json_invalid(self):
        """Test invalid JSON is escaped."""
        from core.safety.validator import SanitizationContext, sanitize_output

        output = sanitize_output("not valid json", SanitizationContext.JSON)

        # Should be wrapped as a JSON string
        assert output.startswith('"')

@pytest.mark.unit
class TestContextDetection:
    """Tests for context detection."""

    def test_detect_html_context(self):
        """Test HTML context detection."""
        from core.safety.validator import OutputSanitizer, SanitizationContext

        sanitizer = OutputSanitizer()
        context = sanitizer.detect_context("/chat/messages")

        assert context == SanitizationContext.HTML

    def test_detect_json_context(self):
        """Test JSON context detection for API routes."""
        from core.safety.validator import OutputSanitizer, SanitizationContext

        sanitizer = OutputSanitizer()
        context = sanitizer.detect_context("/api/agents")

        assert context == SanitizationContext.JSON

    def test_detect_sql_context(self):
        """Test SQL context detection."""
        from core.safety.validator import OutputSanitizer, SanitizationContext

        sanitizer = OutputSanitizer()
        context = sanitizer.detect_context("/query/results")

        assert context == SanitizationContext.SQL

    def test_detect_shell_context(self):
        """Test shell context detection."""
        from core.safety.validator import OutputSanitizer, SanitizationContext

        sanitizer = OutputSanitizer()
        context = sanitizer.detect_context("/execute/command")

        assert context == SanitizationContext.SHELL

@pytest.mark.unit
class TestSafetyLevel:
    """Tests for SafetyLevel enum."""

    def test_safety_levels(self):
        """Test all safety levels exist."""
        from core.safety.validator import SafetyLevel

        assert SafetyLevel.SAFE == "safe"
        assert SafetyLevel.APPROVE == "approve"
        assert SafetyLevel.UNSAFE == "unsafe"
