"""Self-development sandbox for Dryade autonomous improvement.

Enables Dryade to code itself in an isolated environment:
- Sandbox: Isolated workspace fork for development
- Staging: .scratch/ directory for human review
- Signer: Ed25519 signatures for generated skills

Security guarantees:
- AI cannot modify main workspace directly
- All outputs staged for explicit human review
- Full audit trail of all development actions
- Cryptographic signatures for accountability

Usage:
    from core.self_dev import SelfDevSandbox, get_staging_area

    # Enter self-dev mode (explicit command required)
    sandbox = SelfDevSandbox(workspace_path)
    session = await sandbox.enter_self_dev_mode(goal="Create deployment skill")

    # ... AI develops in sandbox ...

    # Stage for human review
    result = await sandbox.validate_and_stage(session, artifacts)
"""

from core.self_dev.sandbox import SelfDevSandbox, SelfDevSession
from core.self_dev.signer import (
    DEFAULT_KEY_DIR,
    SignatureMetadata,
    SignatureResult,
    SkillSigner,
    ensure_user_keypair,
    get_default_signer,
)
from core.self_dev.staging import StagedArtifact, StagingArea, get_staging_area

__all__ = [
    # Sandbox
    "SelfDevSandbox",
    "SelfDevSession",
    # Staging
    "StagingArea",
    "StagedArtifact",
    "get_staging_area",
    # Signer
    "SkillSigner",
    "SignatureResult",
    "SignatureMetadata",
    "get_default_signer",
    "ensure_user_keypair",
    "DEFAULT_KEY_DIR",
]
