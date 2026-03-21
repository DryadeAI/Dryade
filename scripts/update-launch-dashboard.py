#!/usr/bin/env python3
"""Auto-update launch readiness dashboard by checking file existence and git status.

Usage:
    .venv/bin/python scripts/update-launch-dashboard.py

Reads internal-docs/launch-dashboard.md, checks each file-backed checklist item
for existence, updates [ ] to [x] when file exists, updates the timestamp, writes back.
"""

import re
from datetime import UTC, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = ROOT / "internal-docs" / "launch-dashboard.md"

# Maps checklist label substrings to file paths that prove completion.
# When the file exists, the corresponding checklist item is marked [x].
CHECKS: dict[str, Path] = {
    "Messaging narrative finalized": ROOT
    / "internal-docs"
    / "fundraising"
    / "launch-comms"
    / "messaging-narrative.md",
    "All templates rewritten": ROOT
    / "internal-docs"
    / "fundraising"
    / "launch-comms"
    / "messaging-templates.md",
    "Content pipeline reconfigured": ROOT
    / "dryade-plugins"
    / "starter"
    / "content_pipeline"
    / "crew"
    / "prompts"
    / "messaging_context.md",
    "Launch content batch generated": ROOT
    / "internal-docs"
    / "fundraising"
    / "launch-comms"
    / "launch-content-batch.md",
    "Portal audits complete": ROOT / "internal-docs" / "fundraising" / "trails" / "README.md",
    "BPI FTE dossier ready": ROOT
    / "internal-docs"
    / "fundraising"
    / "dossiers"
    / "bpi-fte-dossier.md",
    "NVIDIA Inception application ready": ROOT
    / "internal-docs"
    / "fundraising"
    / "dossiers"
    / "nvidia-inception-dossier.md",
    "Video pitch script written": ROOT
    / "internal-docs"
    / "fundraising"
    / "dossiers"
    / "video-pitch-script.md",
    "Competitive positioning document created": ROOT
    / "internal-docs"
    / "competitive"
    / "positioning-2026.md",
    "Hour-by-hour playbook finalized": ROOT
    / "internal-docs"
    / "fundraising"
    / "launch-comms"
    / "launch-playbook.md",
    "Eval quality gates passing": ROOT
    / "internal-docs"
    / "fundraising"
    / "launch-comms"
    / "eval-results.md",
    "HN Show HN post finalized": ROOT
    / "internal-docs"
    / "fundraising"
    / "launch-comms"
    / "hacker-news-playbook.md",
    "PH page prepared": ROOT
    / "internal-docs"
    / "fundraising"
    / "launch-comms"
    / "product-hunt-playbook.md",
}

def update_dashboard() -> None:
    """Read the dashboard, update checkboxes and timestamp, write back."""
    if not DASHBOARD.exists():
        print(f"ERROR: Dashboard not found at {DASHBOARD}")
        return

    content = DASHBOARD.read_text(encoding="utf-8")

    # Update timestamp
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    content = re.sub(
        r"Last updated: .*",
        f"Last updated: {now}",
        content,
    )

    # Update each checklist item
    for label, filepath in CHECKS.items():
        exists = filepath.exists()
        # Match both checked and unchecked variants
        pattern = re.compile(
            r"- \[([ x])\] " + re.escape(label),
        )
        replacement = f"- [{'x' if exists else ' '}] {label}"
        content = pattern.sub(replacement, content)

    DASHBOARD.write_text(content, encoding="utf-8")

    # Report status
    checked = sum(1 for label, fp in CHECKS.items() if fp.exists())
    total = len(CHECKS)
    print(f"Dashboard updated: {checked}/{total} file-backed items complete")
    print(f"Timestamp: {now}")

    # Show which items are pending
    pending = [label for label, fp in CHECKS.items() if not fp.exists()]
    if pending:
        print(f"\nPending items ({len(pending)}):")
        for item in pending:
            print(f"  - {item}")
    else:
        print("\nAll file-backed items complete!")

if __name__ == "__main__":
    update_dashboard()
