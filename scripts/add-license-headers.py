#!/usr/bin/env python3
"""Add license headers to Dryade source files.

Adds a 2-line copyright + license header to Python and TypeScript files.
Files under core/ee/ get the Enterprise Edition license reference.
All other files get the DSUL license reference.

Usage:
    python scripts/add-license-headers.py              # Dry run (default)
    python scripts/add-license-headers.py --apply       # Apply headers
    python scripts/add-license-headers.py --check       # CI mode: exit 1 if missing
"""

import argparse
import sys
from pathlib import Path

# Header templates
DSUL_HEADER_PY = """\
# Copyright (c) 2025-2026 Dryade SAS
# Licensed under the Dryade Source Use License (DSUL). See LICENSE.
"""

EE_HEADER_PY = """\
# Copyright (c) 2025-2026 Dryade SAS
# Licensed under the Dryade Enterprise Edition License. See LICENSE_EE.md.
"""

DSUL_HEADER_TS = """\
// Copyright (c) 2025-2026 Dryade SAS
// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
"""

# Markers to detect existing headers (any of these means "already has header")
MARKERS = [
    "Copyright (c) 2025-2026 Dryade SAS",
    "Licensed under the Dryade Source Use License",
    "Licensed under the Dryade Enterprise Edition License",
    "Licensed under LICENSE_EE.md",
]

# Directories/patterns to skip
SKIP_DIRS = {
    "__pycache__",
    "node_modules",
    ".venv",
    "dist",
    "build",
    ".next",
    ".git",
    "coverage",
}

# Files to skip (generated, config, etc.)
SKIP_FILES = {
    "vite-env.d.ts",
    "env.d.ts",
    "next-env.d.ts",
}

def has_header(content: str) -> bool:
    """Check if file already has a license header."""
    head = content[:500]
    return any(marker in head for marker in MARKERS)

def should_skip(path: Path) -> bool:
    """Check if file should be skipped."""
    if path.name in SKIP_FILES:
        return True
    for part in path.parts:
        if part in SKIP_DIRS:
            return True
    return False

def is_ee_file(path: Path, core_root: Path) -> bool:
    """Check if file is under core/ee/ directory."""
    try:
        rel = path.relative_to(core_root)
        parts = rel.parts
        return "ee" in parts
    except ValueError:
        return False

def add_header_to_python(content: str, header: str) -> str:
    """Add header to Python file, preserving shebang and encoding."""
    lines = content.split("\n")
    insert_at = 0

    # Preserve shebang line
    if lines and lines[0].startswith("#!"):
        insert_at = 1

    # Preserve encoding declaration
    if insert_at < len(lines) and lines[insert_at].startswith("# -*- coding"):
        insert_at += 1

    result_lines = lines[:insert_at] + header.rstrip("\n").split("\n") + [""] + lines[insert_at:]
    return "\n".join(result_lines)

def add_header_to_typescript(content: str, header: str) -> str:
    """Add header to TypeScript file."""
    return header + content

def process_files(
    root: Path,
    core_root: Path,
    workbench_src: Path,
    apply: bool = False,
    check: bool = False,
) -> tuple[int, int, list[str]]:
    """Process all files. Returns (processed, skipped, missing)."""
    processed = 0
    skipped = 0
    missing: list[str] = []

    # Process Python files in core/
    for py_file in sorted(core_root.rglob("*.py")):
        if should_skip(py_file):
            skipped += 1
            continue

        content = py_file.read_text(encoding="utf-8")
        if has_header(content):
            skipped += 1
            continue

        # Skip empty __init__.py files
        if py_file.name == "__init__.py" and len(content.strip()) == 0:
            skipped += 1
            continue

        header = EE_HEADER_PY if is_ee_file(py_file, core_root) else DSUL_HEADER_PY
        rel_path = py_file.relative_to(root)
        missing.append(str(rel_path))

        if apply:
            new_content = add_header_to_python(content, header)
            py_file.write_text(new_content, encoding="utf-8")
            processed += 1
            print(f"  Added header: {rel_path}")
        elif not check:
            print(f"  Missing header: {rel_path}")
            processed += 1

    # Process TypeScript/TSX files in workbench/src/
    if workbench_src.exists():
        for ext in ("*.ts", "*.tsx"):
            for ts_file in sorted(workbench_src.rglob(ext)):
                if should_skip(ts_file):
                    skipped += 1
                    continue

                content = ts_file.read_text(encoding="utf-8")
                if has_header(content):
                    skipped += 1
                    continue

                rel_path = ts_file.relative_to(root)
                missing.append(str(rel_path))

                if apply:
                    new_content = add_header_to_typescript(content, DSUL_HEADER_TS)
                    ts_file.write_text(new_content, encoding="utf-8")
                    processed += 1
                    print(f"  Added header: {rel_path}")
                elif not check:
                    print(f"  Missing header: {rel_path}")
                    processed += 1

    return processed, skipped, missing

def main() -> int:
    parser = argparse.ArgumentParser(description="Add license headers to Dryade source files")
    parser.add_argument("--apply", action="store_true", help="Apply headers (default: dry run)")
    parser.add_argument("--check", action="store_true", help="CI mode: exit 1 if headers missing")
    args = parser.parse_args()

    root = Path(__file__).parent.parent
    core_root = root / "dryade-core" / "core"
    workbench_src = root / "dryade-workbench" / "src"

    if not core_root.exists():
        print(f"Error: core directory not found at {core_root}")
        return 1

    if not workbench_src.exists():
        print(f"Warning: workbench/src not found at {workbench_src}, skipping TS files")

    mode = "CHECK" if args.check else ("APPLY" if args.apply else "DRY RUN")
    print(f"License header tool [{mode}]")
    print(f"  Core root: {core_root}")
    print(f"  Workbench src: {workbench_src}")
    print()

    processed, skipped, missing = process_files(
        root,
        core_root,
        workbench_src,
        apply=args.apply,
        check=args.check,
    )

    print()
    if args.check:
        if missing:
            print(f"FAIL: {len(missing)} files missing license headers:")
            for f in missing:
                print(f"  {f}")
            return 1
        else:
            print(f"PASS: All files have license headers ({skipped} checked)")
            return 0
    elif args.apply:
        print(f"Done: {processed} headers added, {skipped} already had headers")
    else:
        print(f"Dry run: {processed} files need headers, {skipped} already have them")
        if processed > 0:
            print("Run with --apply to add headers")

    return 0

if __name__ == "__main__":
    sys.exit(main())
