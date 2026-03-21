"""Tests for typo correction (F-002) and leash preset wiring (F-007).

Covers:
- 8 tests for suggest_typo_corrections (common path typo detection)
- 4 tests for leash preset wiring in ComplexHandler
"""

import asyncio
from unittest.mock import MagicMock, patch

from core.orchestrator.typo_correction import suggest_typo_corrections

# ---------------------------------------------------------------
# F-002: Typo correction tests (8 tests)
# ---------------------------------------------------------------

class TestTypoCorrection:
    """Tests for suggest_typo_corrections."""

    def test_corrects_desktop_typo(self):
        corrected, corrections = suggest_typo_corrections("list files on Dekstop")
        assert corrected == "list files on Desktop"
        assert corrections == ["'Dekstop' -> 'Desktop'"]

    def test_corrects_documents_typo(self):
        corrected, corrections = suggest_typo_corrections("save to Docuemnts folder")
        assert "Documents" in corrected
        assert len(corrections) == 1
        assert "'Docuemnts' -> 'Documents'" in corrections

    def test_corrects_downloads_typo(self):
        corrected, corrections = suggest_typo_corrections("check Donwloads")
        assert "Downloads" in corrected
        assert len(corrections) == 1
        assert "'Donwloads' -> 'Downloads'" in corrections

    def test_no_correction_for_correct_paths(self):
        corrected, corrections = suggest_typo_corrections("open my Documents")
        assert corrected == "open my Documents"
        assert corrections == []

    def test_no_correction_for_short_words(self):
        corrected, corrections = suggest_typo_corrections("the cat sat on a mat")
        assert corrected == "the cat sat on a mat"
        assert corrections == []

    def test_corrects_path_inside_filepath(self):
        corrected, corrections = suggest_typo_corrections("read /home/user/Dekstop/file.txt")
        assert "Desktop" in corrected
        assert len(corrections) == 1

    def test_multiple_corrections(self):
        corrected, corrections = suggest_typo_corrections("copy from Dekstop to Donwloads")
        assert "Desktop" in corrected
        assert "Downloads" in corrected
        assert len(corrections) == 2

    def test_case_insensitive_exact_match_no_correction(self):
        corrected, corrections = suggest_typo_corrections("open desktop")
        assert corrected == "open desktop"
        assert corrections == []

# ---------------------------------------------------------------
# F-007: Leash preset wiring tests (4 tests)
# ---------------------------------------------------------------

def _make_context(metadata: dict | None = None) -> MagicMock:
    """Create a mock ExecutionContext with given metadata."""
    ctx = MagicMock()
    ctx.metadata = metadata or {}
    ctx.conversation_id = "test-conv-001"
    ctx.user_id = "test-user"
    return ctx

def _run_handle_and_capture_leash(metadata: dict | None = None):
    """Run ComplexHandler.handle() with mocks and return the leash kwarg.

    Patches DryadeOrchestrator at its source module so the deferred import
    inside handle() picks up the mock.
    """
    from core.orchestrator.handlers.complex_handler import ComplexHandler

    ctx = _make_context(metadata)

    # Mock registry
    mock_registry = MagicMock()
    mock_registry.list_agents.return_value = []

    # Mock orchestrator instance
    mock_orch_instance = MagicMock()
    mock_orch_instance.thinking = MagicMock()
    mock_orch_instance.thinking._on_cost_event = None
    mock_orch_instance.agents = mock_registry

    # Track the DryadeOrchestrator constructor call
    captured_kwargs = {}

    def capture_orch(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return mock_orch_instance

    # Mock config
    mock_config = MagicMock()
    mock_config.planning_enabled = False

    with (
        patch(
            "core.orchestrator.orchestrator.DryadeOrchestrator",
            side_effect=capture_orch,
        ),
        patch(
            "core.adapters.registry.get_registry",
            return_value=mock_registry,
        ),
        patch(
            "core.orchestrator.config.get_orchestration_config",
            return_value=mock_config,
        ),
        patch(
            "core.orchestrator.cancellation.get_cancellation_registry",
        ),
        patch(
            "core.mcp.hierarchical_router.get_hierarchical_router",
            side_effect=Exception("not available"),
        ),
    ):
        handler = ComplexHandler()
        gen = handler.handle("test message", ctx, stream=False)

        # Iterate just one event to trigger the initialization code.
        # Use asyncio.run() to create a fresh event loop -- avoids RuntimeError
        # when prior async tests close the thread event loop (Python 3.12+).
        async def _step():
            try:
                await gen.__anext__()
            except (StopAsyncIteration, Exception):
                pass

        asyncio.run(_step())

    return captured_kwargs.get("leash")

class TestLeashPresetWiring:
    """Tests for leash preset wiring from context.metadata to DryadeOrchestrator."""

    def test_conservative_leash_applied(self):
        from core.autonomous.leash import LEASH_CONSERVATIVE

        leash = _run_handle_and_capture_leash({"leash_preset": "conservative"})
        assert leash is LEASH_CONSERVATIVE

    def test_permissive_leash_applied(self):
        from core.autonomous.leash import LEASH_PERMISSIVE

        leash = _run_handle_and_capture_leash({"leash_preset": "permissive"})
        assert leash is LEASH_PERMISSIVE

    def test_default_leash_when_missing(self):
        from core.autonomous.leash import LEASH_STANDARD

        leash = _run_handle_and_capture_leash({})
        assert leash is LEASH_STANDARD

    def test_unknown_preset_falls_back_to_standard(self):
        from core.autonomous.leash import LEASH_STANDARD

        leash = _run_handle_and_capture_leash({"leash_preset": "yolo"})
        assert leash is LEASH_STANDARD
