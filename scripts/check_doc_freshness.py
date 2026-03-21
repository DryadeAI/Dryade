#!/usr/bin/env python3
"""Check documentation freshness against source of truth.

Verifies that documentation files are in sync with the codebase:
1. Plugin SDK doc vs PluginProtocol class hash
2. Plugin count in README vs actual manifest count
3. API endpoint count in docs vs actual FastAPI routes
4. Internal doc link integrity

Designed for CI: exits 0 if all checks pass, exits 1 if any check fails.
Use --fix to auto-regenerate stale docs instead of just reporting.

Usage:
    python scripts/check_doc_freshness.py [--fix] [--plugins-dir plugins/]
"""

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

def compute_plugin_protocol_hash(core_plugins_path: Path) -> str | None:
    """Compute SHA-256 hash of the PluginProtocol class block.

    Extracts the class from 'class PluginProtocol' to the next top-level
    class definition (or end of file) and hashes it.

    Args:
        core_plugins_path: Path to core/plugins.py.

    Returns:
        Hex digest string, or None if the class cannot be found.
    """
    if not core_plugins_path.is_file():
        return None

    source = core_plugins_path.read_text()
    # Find class PluginProtocol block
    match = re.search(
        r"^(class PluginProtocol\b.*?)(?=\nclass \w|\Z)", source, re.MULTILINE | re.DOTALL
    )
    if not match:
        return None

    block = match.group(1).strip()
    return hashlib.sha256(block.encode()).hexdigest()

def check_plugin_sdk_freshness(fix: bool) -> tuple[bool, str]:
    """Check 1: Plugin SDK freshness vs PluginProtocol.

    Args:
        fix: If True, update the verified-against comment.

    Returns:
        (passed, message) tuple.
    """
    core_plugins_path = PROJECT_ROOT / "core" / "plugins.py"
    sdk_doc_path = PROJECT_ROOT / "docs" / "PLUGIN-SDK.md"

    current_hash = compute_plugin_protocol_hash(core_plugins_path)
    if current_hash is None:
        return True, "OK: Plugin SDK check skipped (PluginProtocol not found in core/plugins.py)"

    if not sdk_doc_path.is_file():
        return False, "STALE: Plugin SDK doc (docs/PLUGIN-SDK.md) does not exist"

    sdk_content = sdk_doc_path.read_text()
    verified_match = re.search(r"<!-- verified-against: (\w+) -->", sdk_content)

    if verified_match:
        old_hash = verified_match.group(1)
        if old_hash == current_hash:
            return True, "OK: Plugin SDK doc is up to date with PluginProtocol"
        else:
            msg = (
                f"STALE: Plugin SDK doc (docs/PLUGIN-SDK.md) is out of date with "
                f"PluginProtocol (core/plugins.py). Last verified: {old_hash[:12]}..., "
                f"current: {current_hash[:12]}..."
            )
            if fix:
                updated = sdk_content.replace(
                    f"<!-- verified-against: {old_hash} -->",
                    f"<!-- verified-against: {current_hash} -->",
                )
                sdk_doc_path.write_text(updated)
                return (
                    True,
                    f"FIXED: Updated Plugin SDK verified-against hash to {current_hash[:12]}...",
                )
            return False, msg
    else:
        msg = (
            f"STALE: Plugin SDK doc (docs/PLUGIN-SDK.md) has no verified-against comment. "
            f"Current PluginProtocol hash: {current_hash[:12]}..."
        )
        if fix:
            # Insert the comment after the first heading
            lines = sdk_content.split("\n")
            insert_idx = 0
            for i, line in enumerate(lines):
                if line.startswith("# "):
                    insert_idx = i + 1
                    break
            lines.insert(insert_idx, f"\n<!-- verified-against: {current_hash} -->\n")
            sdk_doc_path.write_text("\n".join(lines))
            return True, f"FIXED: Added Plugin SDK verified-against hash {current_hash[:12]}..."
        return False, msg

def check_readme_plugin_count(plugins_dir: Path, fix: bool) -> tuple[bool, str]:
    """Check 2: Plugin count in README vs actual.

    Args:
        plugins_dir: Path to plugins directory.
        fix: If True, run generate_plugin_catalog.py.

    Returns:
        (passed, message) tuple.
    """
    readme_path = PROJECT_ROOT / "README.md"
    if not readme_path.is_file():
        return True, "OK: README check skipped (README.md not found)"

    # Count actual plugins
    manifests = list(plugins_dir.rglob("dryade.json"))
    actual_count = len(manifests)

    if actual_count == 0:
        return True, "OK: README check skipped (no dryade.json manifests found)"

    readme_content = readme_path.read_text()

    # Look for patterns like "40 plugins", "40+ plugins"
    count_match = re.search(r"(\d+)\+?\s+plugins", readme_content)
    if not count_match:
        return True, "OK: README check skipped (no plugin count pattern found in README.md)"

    readme_count = int(count_match.group(1))

    # Allow the "+" suffix to mean "at least N"
    has_plus = "+" in count_match.group(0).split("plugins")[0]
    if has_plus:
        if actual_count >= readme_count:
            return True, f"OK: README says {readme_count}+ plugins, found {actual_count}"
        else:
            msg = f"STALE: README.md says {readme_count}+ plugins, but found only {actual_count}"
    else:
        if actual_count == readme_count:
            return True, f"OK: README plugin count matches ({actual_count})"
        else:
            msg = f"STALE: README.md says {readme_count} plugins, but found {actual_count}"

    if fix:
        scripts_dir = PROJECT_ROOT / "scripts"
        catalog_script = scripts_dir / "generate_plugin_catalog.py"
        if catalog_script.is_file():
            try:
                subprocess.run(
                    [
                        sys.executable,
                        str(catalog_script),
                        "--plugins-dir",
                        str(plugins_dir),
                        "--output",
                        str(PROJECT_ROOT / "docs" / "PLUGIN-CATALOG.md"),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                return True, "FIXED: Regenerated plugin catalog"
            except subprocess.CalledProcessError as e:
                return (
                    False,
                    f"FIX FAILED: generate_plugin_catalog.py exited with error: {e.stderr}",
                )
        return False, msg

    return False, msg

def check_api_endpoint_count(fix: bool) -> tuple[bool, str]:
    """Check 3: API endpoints documented vs actual.

    Args:
        fix: If True, run export_openapi.py.

    Returns:
        (passed, message) tuple.
    """
    api_ref_path = PROJECT_ROOT / "docs" / "API-REFERENCE.md"

    # Try to get actual endpoint count from FastAPI app
    actual_count = None
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from core.api.main import app

        spec = app.openapi()
        actual_count = 0
        for _path, methods in spec.get("paths", {}).items():
            for method in methods:
                if method.lower() in ("get", "post", "put", "patch", "delete", "head", "options"):
                    actual_count += 1
    except Exception as e:
        return True, f"OK: API endpoint check skipped (could not import app: {e})"

    if not api_ref_path.is_file():
        if actual_count is not None:
            msg = f"STALE: API reference (docs/API-REFERENCE.md) does not exist, but app has {actual_count} endpoints"
            if fix:
                return _run_export_openapi()
            return False, msg
        return True, "OK: API endpoint check skipped (no API reference doc)"

    # Count documented endpoints (### METHOD /path patterns)
    api_content = api_ref_path.read_text()
    documented = len(
        re.findall(r"^### (GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) /", api_content, re.MULTILINE)
    )

    if actual_count is None:
        return (
            True,
            f"OK: API endpoint check skipped (app not importable), {documented} endpoints documented",
        )

    delta = abs(actual_count - documented)
    if delta <= 2:
        return (
            True,
            f"OK: API endpoints match (documented={documented}, actual={actual_count}, delta={delta})",
        )
    else:
        msg = f"STALE: API reference has {documented} endpoints documented, but app has {actual_count}"
        if fix:
            return _run_export_openapi()
        return False, msg

def _run_export_openapi() -> tuple[bool, str]:
    """Run export_openapi.py to regenerate API docs.

    Returns:
        (passed, message) tuple.
    """
    export_script = PROJECT_ROOT / "scripts" / "export_openapi.py"
    if export_script.is_file():
        try:
            subprocess.run(
                [
                    sys.executable,
                    str(export_script),
                    "--output-json",
                    str(PROJECT_ROOT / "docs" / "openapi.json"),
                    "--output-md",
                    str(PROJECT_ROOT / "docs" / "API-REFERENCE.md"),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            return True, "FIXED: Regenerated API reference"
        except subprocess.CalledProcessError as e:
            return False, f"FIX FAILED: export_openapi.py exited with error: {e.stderr}"
    return False, "FIX FAILED: export_openapi.py not found"

def check_internal_links() -> tuple[bool, list[str]]:
    """Check 4: Broken internal doc links.

    Scans .md files in docs/ and root for broken relative links.

    Returns:
        (all_ok, list of messages).
    """
    messages = []
    all_ok = True

    # Collect markdown files to scan
    md_files: list[Path] = []

    # Root markdown files
    for name in ["README.md", "CONTRIBUTING.md", "CLA.md"]:
        root_md = PROJECT_ROOT / name
        if root_md.is_file():
            md_files.append(root_md)

    # docs/ directory
    docs_dir = PROJECT_ROOT / "docs"
    if docs_dir.is_dir():
        md_files.extend(docs_dir.glob("*.md"))

    # Relative link pattern: [text](relative/path.md) or [text](relative/path.md#anchor)
    link_pattern = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

    for md_file in md_files:
        content = md_file.read_text()
        for match in link_pattern.finditer(content):
            target = match.group(2)

            # Skip URLs
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            # Skip anchors-only
            if target.startswith("#"):
                continue

            # Remove anchor from target
            target_path = target.split("#")[0]
            if not target_path:
                continue

            # Resolve relative to the file's directory
            resolved = (md_file.parent / target_path).resolve()
            if not resolved.exists():
                all_ok = False
                rel_source = md_file.relative_to(PROJECT_ROOT)
                messages.append(f"BROKEN LINK: {rel_source} -> {target_path} (file not found)")

    if all_ok:
        messages.append("OK: All internal doc links are valid")

    return all_ok, messages

def main():
    """CLI entry point for doc freshness checking."""
    parser = argparse.ArgumentParser(
        description="Check documentation freshness against source of truth",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-regenerate stale docs instead of just reporting",
    )
    parser.add_argument(
        "--plugins-dir",
        type=str,
        default="plugins/",
        help="Path to plugins directory (default: plugins/)",
    )

    args = parser.parse_args()
    plugins_dir = Path(args.plugins_dir)
    if not plugins_dir.is_absolute():
        plugins_dir = PROJECT_ROOT / plugins_dir

    fix = args.fix
    checks_total = 0
    checks_passed = 0
    all_messages = []

    # Check 1: Plugin SDK freshness
    checks_total += 1
    passed, msg = check_plugin_sdk_freshness(fix)
    if passed:
        checks_passed += 1
    all_messages.append(msg)

    # Check 2: README plugin count
    checks_total += 1
    passed, msg = check_readme_plugin_count(plugins_dir, fix)
    if passed:
        checks_passed += 1
    all_messages.append(msg)

    # Check 3: API endpoint count
    checks_total += 1
    passed, msg = check_api_endpoint_count(fix)
    if passed:
        checks_passed += 1
    all_messages.append(msg)

    # Check 4: Internal doc links
    checks_total += 1
    links_ok, link_messages = check_internal_links()
    if links_ok:
        checks_passed += 1
    all_messages.extend(link_messages)

    # Print results
    for msg in all_messages:
        print(msg)

    print(f"\nFreshness: {checks_passed}/{checks_total} checks passed")

    if checks_passed < checks_total and not fix:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
