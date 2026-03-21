#!/usr/bin/env python3
"""Register existing factory-scaffolded agents in the factory_artifacts database.

These agents were created on disk by the factory scaffold step but never
registered in the database (the pipeline was interrupted). This script
reads each agent's dryade.json + config.yaml and inserts a FactoryArtifact
record so they appear on the /workspace/factory page.

Usage:
    cd dryade-core && python ../scripts/register-factory-agents.py
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

# Add dryade-core to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "dryade-core"))

import yaml

from core.factory.models import ArtifactStatus, ArtifactType, FactoryArtifact
from core.factory.registry import FactoryRegistry

AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"

def load_agent_info(agent_dir: Path) -> dict:
    """Load agent metadata from dryade.json and config.yaml."""
    manifest = json.loads((agent_dir / "dryade.json").read_text())
    config = yaml.safe_load((agent_dir / "config.yaml").read_text())
    return {"manifest": manifest, "config": config}

def main():
    registry = FactoryRegistry()
    now = datetime.now(UTC)

    agents = sorted(AGENTS_DIR.iterdir())
    if not agents:
        print("No agents found in agents/ directory")
        return

    registered = 0
    skipped = 0

    for agent_dir in agents:
        if not agent_dir.is_dir() or not (agent_dir / "dryade.json").exists():
            continue

        name = agent_dir.name
        info = load_agent_info(agent_dir)
        manifest = info["manifest"]
        config = info["config"]

        # Check if already registered
        existing = registry.get(name)
        if existing:
            print(f"  SKIP  {name} (already registered, status={existing.status.value})")
            skipped += 1
            continue

        description = config.get("description", manifest.get("description", ""))
        framework = config.get("framework", manifest.get("framework", "custom"))
        mcp_servers = config.get("mcp_servers", manifest.get("mcp_servers", []))
        persona = config.get("persona", {})

        artifact = FactoryArtifact(
            id=str(uuid4()),
            name=name,
            artifact_type=ArtifactType.AGENT,
            framework=framework,
            version=1,
            status=ArtifactStatus.SCAFFOLDED,
            source_prompt=description,
            config_json={
                "persona": persona,
                "mcp_servers": mcp_servers,
                "capabilities": config.get("capabilities", []),
                "framework": framework,
            },
            artifact_path=str(agent_dir.relative_to(AGENTS_DIR.parent)),
            test_result=None,
            test_passed=False,
            test_iterations=0,
            created_at=now,
            updated_at=now,
            created_by="factory",
            trigger="user",
            tags=["factory-created", framework] + mcp_servers[:3],
        )

        try:
            artifact_id = registry.register(artifact)
            print(f"  OK    {name} (id={artifact_id[:8]}, framework={framework})")
            registered += 1
        except Exception as e:
            print(f"  FAIL  {name}: {e}")

    print(f"\nDone: {registered} registered, {skipped} skipped")

if __name__ == "__main__":
    main()
