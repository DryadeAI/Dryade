#!/usr/bin/env bash
# ci-audit-precommit.sh — Pre-commit hook wrapper for scoped checks
# Called by .pre-commit-config.yaml hooks that need subdirectory scoping.
set -euo pipefail

CMD="${1:?Usage: ci-audit-precommit.sh <eslint|mypy>}"

# Get staged files (relative to repo root)
staged_files() {
  git diff --cached --name-only --diff-filter=ACM
}

case "$CMD" in
  eslint)
    # Get staged .ts/.tsx files under dryade-workbench/
    FILES=$(staged_files | grep '^dryade-workbench/.*\.\(ts\|tsx\)$' || true)
    if [ -z "$FILES" ]; then
      exit 0  # No workbench files staged
    fi
    # Strip prefix for eslint (it runs from workbench dir)
    RELATIVE=$(echo "$FILES" | sed 's|^dryade-workbench/||')
    cd dryade-workbench
    # Run eslint --fix, then re-stage fixed files
    echo "$RELATIVE" | xargs npx eslint --fix 2>&1 || true
    cd ..
    # Re-stage any auto-fixed files
    echo "$FILES" | xargs git add
    # Re-run without --fix to check for remaining errors
    RELATIVE=$(echo "$FILES" | sed 's|^dryade-workbench/||')
    cd dryade-workbench
    echo "$RELATIVE" | xargs npx eslint
    ;;

  mypy)
    # Get staged .py files under dryade-core/core/
    FILES=$(staged_files | grep '^dryade-core/core/.*\.py$' || true)
    if [ -z "$FILES" ]; then
      exit 0  # No core Python files staged
    fi
    # Run mypy on staged files only (incremental cache speeds this up)
    uv run mypy --incremental $FILES
    ;;

  *)
    echo "Unknown command: $CMD"
    echo "Usage: ci-audit-precommit.sh <eslint|mypy>"
    exit 1
    ;;
esac
