"""Ed25519 skill signing for verification and accountability.

Security model:
- External/downloaded skills: MUST have valid signature from trusted source
- User-created skills: Require self-signing (creates accountability)
- Bundled skills: Signed during build process

Ed25519 chosen because:
- Fast signature generation and verification
- Small key size (32 bytes)
- High security (128-bit equivalent)
- Widely supported and audited
"""

import contextlib
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from core.utils.time import utcnow

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

@dataclass
class SignatureResult:
    """Result of signature verification."""

    valid: bool
    reason: str | None = None
    signer_id: str | None = None
    signed_at: datetime | None = None

@dataclass
class SignatureMetadata:
    """Metadata stored with signature."""

    signer_id: str
    signed_at: str
    content_hash: str
    public_key_fingerprint: str
    version: str = "1"

class SkillSigner:
    """Ed25519 signature management for skills.

    Skills are signed by hashing their content deterministically,
    then signing the hash with Ed25519. The signature is stored
    as a detached .signature file alongside SKILL.md.

    Usage:
        signer = SkillSigner()

        # Generate keypair for user
        private_key, public_key = signer.generate_keypair()
        signer.save_keypair(private_key, public_key, "~/.dryade/keys/")

        # Sign a skill
        signature = signer.sign_skill(skill_dir, private_key, signer_id="user@example.com")

        # Verify a skill
        result = signer.verify_skill(skill_dir, public_key)
        if result.valid:
            print(f"Signed by {result.signer_id}")
    """

    SIGNATURE_FILE = ".signature"
    SIGNATURE_VERSION = "1"

    def generate_keypair(self) -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
        """Generate Ed25519 keypair.

        Returns:
            (private_key, public_key) tuple
        """
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        return private_key, public_key

    def save_keypair(
        self,
        private_key: Ed25519PrivateKey,
        public_key: Ed25519PublicKey,
        key_dir: Path | str,
        password: bytes | None = None,
    ) -> tuple[Path, Path]:
        """Save keypair to files.

        Args:
            private_key: Private key to save
            public_key: Public key to save
            key_dir: Directory for key files
            password: Optional password for private key encryption

        Returns:
            (private_key_path, public_key_path)
        """
        key_dir = Path(key_dir).expanduser()
        key_dir.mkdir(parents=True, exist_ok=True)

        # Save private key (encrypted if password provided)
        private_path = key_dir / "skill_signing.key"
        encryption = (
            serialization.BestAvailableEncryption(password)
            if password
            else serialization.NoEncryption()
        )
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=encryption,
        )
        private_path.write_bytes(private_pem)
        private_path.chmod(0o600)  # Owner read/write only

        # Save public key
        public_path = key_dir / "skill_signing.pub"
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        public_path.write_bytes(public_pem)

        logger.info(f"[Signer] Saved keypair to {key_dir}")
        return private_path, public_path

    def load_private_key(
        self,
        key_path: Path | str,
        password: bytes | None = None,
    ) -> Ed25519PrivateKey:
        """Load private key from file.

        Args:
            key_path: Path to private key file
            password: Password if key is encrypted

        Returns:
            Loaded private key
        """
        key_path = Path(key_path).expanduser()
        key_data = key_path.read_bytes()
        private_key = serialization.load_pem_private_key(key_data, password=password)

        if not isinstance(private_key, Ed25519PrivateKey):
            raise ValueError("Key is not Ed25519")

        return private_key

    def load_public_key(self, key_path: Path | str) -> Ed25519PublicKey:
        """Load public key from file.

        Args:
            key_path: Path to public key file

        Returns:
            Loaded public key
        """
        key_path = Path(key_path).expanduser()
        key_data = key_path.read_bytes()
        public_key = serialization.load_pem_public_key(key_data)

        if not isinstance(public_key, Ed25519PublicKey):
            raise ValueError("Key is not Ed25519")

        return public_key

    def _hash_skill_content(self, skill_dir: Path) -> bytes:
        """Compute deterministic hash of skill content.

        Hashes:
        1. SKILL.md content
        2. scripts/ directory contents (sorted)
        3. references/ directory contents (sorted)

        Args:
            skill_dir: Path to skill directory

        Returns:
            SHA-256 hash bytes
        """
        hasher = hashlib.sha256()

        # 1. Hash SKILL.md
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            hasher.update(b"SKILL.md:")
            hasher.update(skill_md.read_bytes())

        # 2. Hash scripts/ (sorted for determinism)
        scripts_dir = skill_dir / "scripts"
        if scripts_dir.exists():
            for script in sorted(scripts_dir.rglob("*")):
                if script.is_file():
                    relative = str(script.relative_to(skill_dir))
                    hasher.update(f"scripts:{relative}:".encode())
                    hasher.update(script.read_bytes())

        # 3. Hash references/ (sorted for determinism)
        refs_dir = skill_dir / "references"
        if refs_dir.exists():
            for ref in sorted(refs_dir.rglob("*")):
                if ref.is_file():
                    relative = str(ref.relative_to(skill_dir))
                    hasher.update(f"references:{relative}:".encode())
                    hasher.update(ref.read_bytes())

        return hasher.digest()

    def _get_key_fingerprint(self, public_key: Ed25519PublicKey) -> str:
        """Get fingerprint of public key.

        Args:
            public_key: Key to fingerprint

        Returns:
            Hex fingerprint (first 16 chars of SHA-256)
        """
        key_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return hashlib.sha256(key_bytes).hexdigest()[:16]

    def sign_skill(
        self,
        skill_dir: Path | str,
        private_key: Ed25519PrivateKey,
        signer_id: str,
    ) -> str:
        """Sign a skill directory.

        Creates a .signature file in the skill directory containing
        the Ed25519 signature and metadata.

        Args:
            skill_dir: Path to skill directory
            private_key: Signing key
            signer_id: Identifier for signer (email, username, etc.)

        Returns:
            Signature as hex string
        """
        skill_dir = Path(skill_dir)

        if not (skill_dir / "SKILL.md").exists():
            raise ValueError(f"No SKILL.md in {skill_dir}")

        # Hash skill content
        content_hash = self._hash_skill_content(skill_dir)

        # Sign the hash
        signature = private_key.sign(content_hash)
        signature_hex = signature.hex()

        # Create metadata
        public_key = private_key.public_key()
        metadata = SignatureMetadata(
            signer_id=signer_id,
            signed_at=utcnow().isoformat(),
            content_hash=content_hash.hex(),
            public_key_fingerprint=self._get_key_fingerprint(public_key),
            version=self.SIGNATURE_VERSION,
        )

        # Write signature file
        signature_data = {
            "signature": signature_hex,
            "metadata": {
                "signer_id": metadata.signer_id,
                "signed_at": metadata.signed_at,
                "content_hash": metadata.content_hash,
                "public_key_fingerprint": metadata.public_key_fingerprint,
                "version": metadata.version,
            },
        }

        signature_path = skill_dir / self.SIGNATURE_FILE
        signature_path.write_text(json.dumps(signature_data, indent=2))

        logger.info(f"[Signer] Signed skill: {skill_dir.name} by {signer_id}")
        return signature_hex

    def verify_skill(
        self,
        skill_dir: Path | str,
        public_key: Ed25519PublicKey,
    ) -> SignatureResult:
        """Verify a skill's signature.

        Args:
            skill_dir: Path to skill directory
            public_key: Public key to verify against

        Returns:
            SignatureResult with verification status
        """
        skill_dir = Path(skill_dir)
        signature_path = skill_dir / self.SIGNATURE_FILE

        # Check signature file exists
        if not signature_path.exists():
            return SignatureResult(
                valid=False,
                reason="No signature file found",
            )

        # Load signature data
        try:
            signature_data = json.loads(signature_path.read_text())
            signature_hex = signature_data["signature"]
            metadata = signature_data["metadata"]
        except (json.JSONDecodeError, KeyError) as e:
            return SignatureResult(
                valid=False,
                reason=f"Invalid signature file: {e}",
            )

        # Verify key fingerprint matches
        expected_fingerprint = self._get_key_fingerprint(public_key)
        if metadata.get("public_key_fingerprint") != expected_fingerprint:
            return SignatureResult(
                valid=False,
                reason="Public key fingerprint mismatch",
            )

        # Hash current content
        content_hash = self._hash_skill_content(skill_dir)

        # Verify content hash matches
        if content_hash.hex() != metadata.get("content_hash"):
            return SignatureResult(
                valid=False,
                reason="Content has been modified since signing",
            )

        # Verify signature
        try:
            signature = bytes.fromhex(signature_hex)
            public_key.verify(signature, content_hash)
        except Exception as e:
            return SignatureResult(
                valid=False,
                reason=f"Signature verification failed: {e}",
            )

        # Parse signed_at
        signed_at = None
        if metadata.get("signed_at"):
            with contextlib.suppress(ValueError):
                signed_at = datetime.fromisoformat(metadata["signed_at"])

        return SignatureResult(
            valid=True,
            signer_id=metadata.get("signer_id"),
            signed_at=signed_at,
        )

    def is_skill_signed(self, skill_dir: Path | str) -> bool:
        """Check if skill has a signature file.

        Args:
            skill_dir: Path to skill directory

        Returns:
            True if .signature file exists
        """
        return (Path(skill_dir) / self.SIGNATURE_FILE).exists()

    def get_signature_metadata(self, skill_dir: Path | str) -> dict | None:
        """Get signature metadata without verification.

        Args:
            skill_dir: Path to skill directory

        Returns:
            Metadata dict or None if not signed
        """
        signature_path = Path(skill_dir) / self.SIGNATURE_FILE
        if not signature_path.exists():
            return None

        try:
            data = json.loads(signature_path.read_text())
            return data.get("metadata")
        except Exception:
            return None

# Default key locations
DEFAULT_KEY_DIR = Path.home() / ".dryade" / "keys"

def get_default_signer() -> SkillSigner:
    """Get default skill signer instance.

    Returns:
        SkillSigner instance
    """
    return SkillSigner()

def ensure_user_keypair(
    key_dir: Path | None = None,
    password: bytes | None = None,
) -> tuple[Path, Path]:
    """Ensure user has a keypair for signing.

    Creates keypair if not exists.

    Args:
        key_dir: Key directory (default: ~/.dryade/keys/)
        password: Password for private key

    Returns:
        (private_key_path, public_key_path)
    """
    key_dir = key_dir or DEFAULT_KEY_DIR
    private_path = key_dir / "skill_signing.key"
    public_path = key_dir / "skill_signing.pub"

    if private_path.exists() and public_path.exists():
        return private_path, public_path

    # Generate new keypair
    signer = SkillSigner()
    private_key, public_key = signer.generate_keypair()
    return signer.save_keypair(private_key, public_key, key_dir, password)
