#!/usr/bin/env python3
"""Per-file coverage minimum enforcement script.

Parses a Cobertura XML coverage report and enforces a minimum line coverage
threshold per file. Exits with code 1 if any non-exempt file falls below the
minimum.

Usage:
    python tests/scripts/check_per_file_coverage.py [--xml coverage.xml] [--minimum 70]
    python tests/scripts/check_per_file_coverage.py --paths core/auth/ --minimum 80
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Paths containing these fragments are exempt from per-file enforcement.
# These match the omit patterns from pyproject.toml plus test/generated paths.
EXEMPT_FRAGMENTS = [
    # Test infrastructure
    "tests/",
    "/tests/",
    "tests\\",
    # Scripts and generated code
    "scripts/",
    "migrations/",
    "__pycache__/",
    # Eval tests (LLM-dependent, not unit-testable)
    "tests/eval/",
    # Capella (requires external Capella infrastructure)
    "core/mcp/capella",
    "capella_model_utils.py",
    "capella_schema.py",
    # Deprecated modules
    "core/crews/",
    "core/crew/",
    # CLI (tested separately)
    "core/cli/",
    # Domain-specific stubs (auto-generated)
    "core/domains/",
    # Integration-heavy modules at 0% (need full integration tests)
    "core/autonomous/chat_adapter.py",
    "core/adapters/auto_discovery.py",
    "core/adapters/zero_dev.py",
    "core/orchestrator/planning.py",
    "core/orchestrator/memory.py",
    "core/orchestrator/complexity.py",
    "core/orchestrator/context.py",
    "core/orchestrator/cancellation.py",
    "core/orchestrator/stream_registry.py",
    "core/skills/tool.py",
    # Capella API routes (requires Capella infrastructure)
    "core/api/routes/capella",
    # MCP transport/registry — require live subprocess/process management
    "core/mcp/registry.py",
    "core/mcp/stdio_transport.py",
    "core/mcp/http_transport.py",
    "core/mcp/self_mod.py",
    "core/mcp/setup_wizard.py",
    "core/mcp/tool_wrapper.py",
    # MCP server integrations — each requires external service
    "core/mcp/servers/grafana.py",
    "core/mcp/servers/github.py",
    "core/mcp/servers/dbhub.py",
    "core/mcp/servers/context7.py",
    "core/mcp/servers/linear.py",
    "core/mcp/servers/document_ops.py",
    "core/mcp/servers/filesystem.py",
    "core/mcp/servers/git.py",
    "core/mcp/servers/memory.py",
    "core/mcp/servers/pdf_reader.py",
    "core/mcp/servers/playwright.py",
    # Workflow execution engine — requires live agent/tool orchestration
    "core/workflows/executor.py",
    "core/workflows/triggers.py",
    # API routes requiring full integration stack (LLM, Redis, Qdrant, etc.)
    "core/api/routes/knowledge.py",
    "core/api/routes/agents.py",
    "core/api/routes/flows.py",
    "core/api/routes/factory.py",
    "core/api/routes/cache.py",
    "core/api/routes/marketplace.py",
    "core/api/routes/custom_providers.py",
    "core/api/routes/commands.py",
    "core/api/routes/mfa.py",
    "core/api/routes/models_config.py",
    "core/api/routes/metrics_api.py",
    "core/api/routes/websocket.py",
    "core/api/routes/workflow_scenarios.py",
    "core/api/routes/provider_registry.py",
    "core/api/routes/projects.py",
    "core/api/routes/sandbox.py",
    "core/api/routes/security_telemetry.py",
    "core/api/routes/users.py",
    "core/api/routes/skills.py",
    "core/api/routes/extensions.py",
    "core/api/routes/plans.py",
    "core/api/routes/plugins.py",
    "core/api/routes/workflows.py",
    "core/api/routes/chat.py",
    # core/api/routes/auth.py: removed from exemption in Phase 149 (auth sub-gate scope)
    "core/api/routes/health.py",
    # Middleware requiring live Redis/external deps
    "core/api/middleware/llm_config.py",
    # Adapter — heavy A2A protocol integration
    "core/adapters/a2a_adapter.py",
    # Adapter requiring live CrewAI/agent infrastructure
    "core/adapters/crewai_adapter.py",
    # Knowledge pipeline — requires Qdrant vector DB
    "core/knowledge/embedder.py",
    "core/knowledge/storage.py",
    "core/knowledge/pipeline.py",
    "core/knowledge/context.py",
    "core/knowledge/sources.py",
    # Database migration (requires Alembic/DB connection)
    "core/database/migrate.py",
    # Orchestrator modules requiring live services
    "core/orchestrator/memory_tools.py",
    "core/orchestrator/continuous_loop.py",
    "core/orchestrator/router.py",
    "core/orchestrator/planner.py",
    # MCP modules requiring live services
    "core/mcp/credentials.py",
    "core/mcp/autoload.py",
    "core/mcp/gateway/server.py",
    "core/mcp/gateway/__init__.py",
    "core/mcp/domain.py",
    "core/mcp/embeddings.py",
    "core/mcp/nl_query.py",
    "core/mcp/tool_index.py",
    "core/mcp/capability_cache.py",
    "core/mcp/config.py",
    "core/mcp/hierarchical_router.py",
    # Auth modules: removed from exemption in Phase 149 (now sub-gated at 80%)
    # Skills filesystem watcher (requires real filesystem events)
    "core/skills/watcher.py",
    # Autonomous executor (requires full agent execution loop)
    "core/autonomous/executor.py",
]

def is_exempt(filename: str) -> bool:
    """Return True if the file should be excluded from per-file enforcement."""
    normalized = filename.replace("\\", "/")
    return any(fragment in normalized for fragment in EXEMPT_FRAGMENTS)

def _resolve_filename(filename: str, sources: list[str]) -> str:
    """Resolve a bare XML filename to its full path using source directories.

    When coverage.py uses multiple source roots, XML filenames are relative to
    each source root (e.g., 'service.py' instead of 'core/auth/service.py').
    This function checks which source directory contains the file on disk and
    returns the full relative path from the project root.
    """
    if "/" in filename or "\\" in filename:
        return filename  # Already has path components

    for source in sources:
        candidate = Path(source) / filename
        if candidate.exists():
            return str(candidate)

    return filename  # Fallback to bare name

def parse_coverage_xml(xml_path: str) -> list[tuple[str, float, int, int]]:
    """Parse Cobertura XML and return list of (filename, line_rate, hits, total) tuples."""
    try:
        tree = ET.parse(xml_path)  # noqa: S314
    except FileNotFoundError:
        print(f"ERROR: Coverage XML not found: {xml_path}", file=sys.stderr)
        sys.exit(2)
    except ET.ParseError as exc:
        print(f"ERROR: Failed to parse coverage XML: {exc}", file=sys.stderr)
        sys.exit(2)

    root = tree.getroot()
    results = []

    # Extract source directories for filename resolution
    sources = [s.text for s in root.findall(".//source") if s.text]

    # Cobertura format: <coverage><packages><package><classes><class filename="..." line-rate="0.85">
    for class_elem in root.iter("class"):
        filename = class_elem.get("filename", "")
        line_rate_str = class_elem.get("line-rate", "1.0")
        try:
            line_rate = float(line_rate_str)
        except ValueError:
            line_rate = 1.0

        # Count lines for context
        lines = class_elem.findall(".//line")
        total = len(lines)
        hits = sum(1 for line in lines if int(line.get("hits", "0")) > 0)

        if filename:
            resolved = _resolve_filename(filename, sources)
            results.append((resolved, line_rate, hits, total))

    return results

def check_coverage(xml_path: str, minimum: float, paths: list[str] | None = None) -> int:
    """Check per-file coverage. Returns 0 if all pass, 1 if any violations found."""
    entries = parse_coverage_xml(xml_path)

    if not entries:
        print("WARNING: No files found in coverage report.")
        return 0

    violations: list[tuple[str, float]] = []
    checked = 0
    exempted = 0

    for filename, line_rate, hits, total in sorted(entries):
        if is_exempt(filename):
            exempted += 1
            continue

        # Apply path filter if specified (for sub-gate mode)
        if paths:
            normalized = filename.replace("\\", "/")
            if not any(frag in normalized for frag in paths):
                continue

        checked += 1
        percentage = line_rate * 100.0

        if percentage < minimum:
            violations.append((filename, percentage))

    # Safety check: --paths with 0 matches is a misconfiguration, not a pass
    if paths and checked == 0:
        print(
            "\nERROR: --paths filter matched 0 files. Verify auth modules are not excluded from coverage.",
            file=sys.stderr,
        )
        print(f"  Paths filter: {paths}", file=sys.stderr)
        return 1

    # Report violations
    if violations:
        print(
            f"\nPer-file coverage FAILED: {len(violations)} file(s) below {minimum:.0f}% minimum\n"
        )
        if paths:
            paths_desc = ", ".join(paths)
            print(f"  (filtered to paths: {paths_desc})")
        print(f"{'Coverage':>10}  File")
        print(f"{'--------':>10}  ----")
        for filename, pct in sorted(violations, key=lambda x: x[1]):
            print(f"{pct:>9.1f}%  {filename}")
        print(f"\n{checked} files checked, {exempted} exempted, {len(violations)} violation(s)\n")
        return 1
    else:
        msg = (
            f"Per-file coverage OK: all {checked} tracked files meet {minimum:.0f}% minimum"
            f" ({exempted} exempted)"
        )
        print(msg)
        if paths:
            paths_desc = ", ".join(paths)
            print(f"  (filtered to paths: {paths_desc})")
        return 0

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enforce per-file minimum line coverage from a Cobertura XML report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--xml",
        default="coverage.xml",
        help="Path to Cobertura XML coverage report (default: coverage.xml)",
    )
    parser.add_argument(
        "--minimum",
        type=float,
        default=70.0,
        help="Minimum line coverage percentage per file (default: 70)",
    )
    parser.add_argument(
        "--paths",
        nargs="+",
        default=None,
        metavar="PATH_FRAGMENT",
        help="Only check files whose path contains any of these fragments (for sub-gate enforcement)",
    )
    args = parser.parse_args()

    if args.minimum < 0 or args.minimum > 100:
        print("ERROR: --minimum must be between 0 and 100", file=sys.stderr)
        sys.exit(2)

    xml_path = Path(args.xml)
    exit_code = check_coverage(str(xml_path), args.minimum, args.paths)
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
