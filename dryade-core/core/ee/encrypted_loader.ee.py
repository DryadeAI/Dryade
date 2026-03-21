# Copyright (c) 2025-2026 Dryade SAS
# Licensed under the Dryade Enterprise Edition License. See LICENSE_EE.md.
"""Memory-only decryption and loading of .dryadepkg packages.

Security model:
- Encrypted .dryadepkg files stay encrypted on disk permanently.
- Decryption happens in memory only via memfd_create (Linux) or tmpfs-backed
  temp files (cross-platform fallback).
- Compiled .so modules are loaded from the memory file descriptor without
  touching the regular filesystem.
- On process exit, decrypted code is gone from memory — no disk residue.

Exports:
    load_encrypted_plugin   — Main entry point: decrypt + import plugin
    decrypt_and_extract_payload — Decrypt .dryadepkg and return {filename: bytes}
    load_so_from_memory     — Load a .so from memory bytes via memfd
    MemoryModuleLoader      — importlib hook for in-memory module serving
    SecurityError           — Raised on signature verification failure
    _memfd_create           — Low-level memfd_create syscall (Linux) with fallback
"""

from __future__ import annotations

import ctypes
import importlib.abc
import importlib.util
import io
import logging
import os
import sys
import tarfile
import tempfile
import types
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Architecture → syscall number map for memfd_create ───────────────────────
# sys_memfd_create (319 on x86_64, 279 on aarch64, 385 on arm32, 356 on s390x)
_MEMFD_SYSCALL = {
    "x86_64": 319,
    "aarch64": 279,
    "arm": 385,
    "s390x": 356,
    "ppc64le": 360,
    "riscv64": 279,
}
_MFD_CLOEXEC = 0x0001

# ── Exceptions ────────────────────────────────────────────────────────────────

class SecurityError(Exception):
    """Raised when an Ed25519 signature verification fails for a .dryadepkg."""

# ── Low-level: memory file descriptor ─────────────────────────────────────────

def _memfd_create(name: str) -> int:
    """Create an anonymous memory-backed file descriptor.

    On Linux, uses the memfd_create(2) syscall which creates a RAM-backed fd
    that is never visible in the filesystem namespace (not even /proc/self/fd
    exposes readable content — only the fd number).

    On non-Linux platforms, or if the syscall fails, falls back to a tmpfs-
    backed NamedTemporaryFile opened in O_RDWR mode.  The temp file is created
    with delete=False so that we can control its lifetime; callers must
    os.close() the fd and ensure the backing file is removed when done.

    Args:
        name: Descriptive name embedded in the memfd (visible in /proc/self/fd/).

    Returns:
        An open, writable file descriptor (int).  Position starts at 0.
    """
    if sys.platform == "linux":
        machine = os.uname().machine
        syscall_nr = _MEMFD_SYSCALL.get(machine)
        if syscall_nr is not None:
            try:
                libc = ctypes.CDLL("libc.so.6", use_errno=True)
                fd = libc.syscall(syscall_nr, name.encode("utf-8"), _MFD_CLOEXEC)
                if fd >= 0:
                    return fd
                # syscall returned error — fall through to tmpfs fallback
                errno = ctypes.get_errno()
                logger.debug("memfd_create syscall failed (errno=%d), using tmpfs fallback", errno)
            except (OSError, AttributeError) as exc:
                logger.debug("memfd_create unavailable (%s), using tmpfs fallback", exc)

    # Fallback: use /dev/shm (tmpfs on Linux) if available, else system temp dir.
    shm_dir = "/dev/shm" if os.path.isdir("/dev/shm") else None
    tf = tempfile.NamedTemporaryFile(
        dir=shm_dir,
        prefix=f"dryadepkg_{name}_",
        delete=False,
        suffix=".mem",
    )
    fd = os.dup(tf.fileno())  # dup so we can close the NamedTemporaryFile wrapper
    tf.close()
    # Unlink immediately — fd stays open, file disappears from directory
    try:
        os.unlink(tf.name)
    except OSError:
        pass
    return fd

# ── Load compiled .so from memory ─────────────────────────────────────────────

def load_so_from_memory(so_bytes: bytes, module_name: str) -> types.ModuleType:
    """Load a compiled .so (or any importable file) from raw bytes in memory.

    On Linux, writes so_bytes to a memfd and imports via /proc/self/fd/<fd>.
    On other platforms, falls back to a tmpfs temp file that is unlinked
    immediately after import (the .so stays loaded in the process).

    Args:
        so_bytes: Raw bytes of the compiled extension module.
        module_name: Python module name for sys.modules registration.

    Returns:
        Imported module object.

    Raises:
        ImportError: If the module cannot be imported from the bytes.
    """
    fd = _memfd_create(module_name)
    try:
        os.write(fd, so_bytes)
        os.lseek(fd, 0, os.SEEK_SET)

        # On Linux, /proc/self/fd/{fd} is a stable symlink to the memfd
        proc_path = f"/proc/self/fd/{fd}"
        if os.path.exists(proc_path):
            spec = importlib.util.spec_from_file_location(module_name, proc_path)
        else:
            # Cross-platform: write to a separate tmpfs temp file for import
            # The fd we already have is just for the bytes; create a named path.
            with tempfile.NamedTemporaryFile(
                suffix=".so",
                delete=False,
                dir="/dev/shm" if os.path.isdir("/dev/shm") else None,
            ) as tf:
                tf.write(so_bytes)
                tmp_path = tf.name
            try:
                spec = importlib.util.spec_from_file_location(module_name, tmp_path)
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create import spec for {module_name} from memory")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module

    finally:
        try:
            os.close(fd)
        except OSError:
            pass

# ── Decrypt and extract tar.gz payload ────────────────────────────────────────

def decrypt_and_extract_payload(
    pkg_bytes: bytes,
    encryption_key: bytes,
    *,
    mlkem_secret_key: bytes | None = None,
) -> dict[str, bytes]:
    """Decrypt a .dryadepkg payload and extract its files entirely in memory.

    Supports both classical AES-256-GCM and hybrid ML-KEM-1024 + AES-256-GCM
    encryption. Format is auto-detected: if mlkem_secret_key is provided and
    the payload header indicates ML-KEM format, hybrid decryption is used.
    Otherwise falls back to classical AES-256-GCM.

    Args:
        pkg_bytes: Raw bytes of the .dryadepkg container (from disk read).
        encryption_key: 32-byte AES-256-GCM key (classical path).
        mlkem_secret_key: Optional ML-KEM-1024 secret key for hybrid decryption.

    Returns:
        dict mapping filename -> file bytes. All extraction happens in RAM.

    Raises:
        ValueError: Decryption failed (bad key or corrupted data).
        tarfile.TarError: Payload is not a valid tar.gz archive.
    """
    from core.ee.dryadepkg_format import decrypt_dryadepkg_payload

    # Try hybrid decryption first if ML-KEM key is provided
    if mlkem_secret_key is not None:
        try:
            from core.ee.crypto.pq import ML_KEM_1024_CT_SIZE, hybrid_decrypt

            # Check if payload is large enough to be hybrid-encrypted
            if len(pkg_bytes) > ML_KEM_1024_CT_SIZE:
                decrypted_bytes = hybrid_decrypt(pkg_bytes, mlkem_secret_key)
                logger.debug("Decrypted payload using ML-KEM hybrid encryption")
            else:
                # Too small for hybrid — fall back to classical
                decrypted_bytes = decrypt_dryadepkg_payload(pkg_bytes, encryption_key)
        except Exception:
            # Hybrid failed — fall back to classical (backward compat)
            logger.debug("Hybrid decryption failed, falling back to classical AES-GCM")
            decrypted_bytes = decrypt_dryadepkg_payload(pkg_bytes, encryption_key)
    else:
        decrypted_bytes = decrypt_dryadepkg_payload(pkg_bytes, encryption_key)

    # Extract tar.gz entirely in memory — never write to disk
    file_dict: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(decrypted_bytes), mode="r:gz") as tf:
        for member in tf.getmembers():
            if member.isfile():
                fobj = tf.extractfile(member)
                if fobj is not None:
                    file_dict[member.name] = fobj.read()

    return file_dict

# ── MemoryModuleLoader: importlib hook ────────────────────────────────────────

class MemoryModuleLoader(importlib.abc.Loader):
    """importlib meta-path hook that serves modules from an in-memory dict.

    Register an instance in sys.meta_path so that imports within an encrypted
    plugin namespace are served from already-loaded module objects rather than
    from disk.

    Usage:
        loader = MemoryModuleLoader({"my_plugin": module_obj})
        sys.meta_path.insert(0, loader)
    """

    def __init__(self, module_map: dict[str, types.ModuleType]) -> None:
        """Initialise with a mapping of fully-qualified name -> module object.

        Args:
            module_map: {module_name: module_object} for all pre-loaded modules.
        """
        self._module_map = module_map

    # ── Legacy finder/loader API (importlib.abc.Loader + find_module) ────────

    def find_module(
        self,
        fullname: str,
        path: object = None,  # noqa: ARG002
    ) -> "MemoryModuleLoader | None":
        """Return self if we handle fullname, else None.

        Args:
            fullname: Fully-qualified module name (e.g. 'my_plugin.utils').
            path: Ignored -- in-memory modules have no filesystem path.

        Returns:
            self if fullname is in our module_map, else None.
        """
        if fullname in self._module_map:
            return self
        return None

    def load_module(self, fullname: str) -> types.ModuleType:
        """Return the pre-loaded module for fullname.

        Also registers the module in sys.modules so subsequent imports hit
        the module cache directly.

        Args:
            fullname: Fully-qualified module name.

        Returns:
            The module object.

        Raises:
            ImportError: If fullname is not in our module_map.
        """
        if fullname not in self._module_map:
            raise ImportError(f"MemoryModuleLoader: no in-memory module '{fullname}'")
        module = self._module_map[fullname]
        sys.modules[fullname] = module
        return module

    # ── Modern loader API (exec_module / create_module) ──────────────────────

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> types.ModuleType | None:
        """Return pre-loaded module if available, else None (use default creation)."""
        return self._module_map.get(spec.name)

    def exec_module(self, module: types.ModuleType) -> None:
        """No-op: module was already executed when loaded from memory."""

# ── Main public API ───────────────────────────────────────────────────────────

def load_encrypted_plugin(
    pkg_path: Path,
    encryption_key: bytes,
    author_public_key: object | None = None,
) -> types.ModuleType:
    """Load a .dryadepkg v2 package as a Python module, decrypting in memory only.

    Steps:
    1. Read encrypted .dryadepkg from disk (only disk access).
    2. Optionally verify Ed25519 author signature -- raise SecurityError if invalid.
    3. Decrypt payload in memory via AES-256-GCM.
    4. Extract tar.gz in memory -> {filename: bytes}.
    5. For .so files: load via load_so_from_memory() (memfd, no disk write).
    6. For .py files (plaintext): compile and exec into module object in memory.
    7. Register MemoryModuleLoader in sys.meta_path for intra-plugin imports.
    8. Return the top-level plugin module.

    Args:
        pkg_path: Path to the encrypted .dryadepkg file on disk.
        encryption_key: 32-byte AES-256 key for decryption.
        author_public_key: Optional Ed25519PublicKey to verify author signature.
            If None, signature check is skipped (dev mode).

    Returns:
        The top-level plugin module.

    Raises:
        SecurityError: If author_public_key is provided and signature is invalid.
        ValueError: If decryption fails (wrong key or corrupted data).
        ImportError: If no valid entry-point module is found in the package.
    """
    pkg_bytes = Path(pkg_path).read_bytes()

    # 1. Signature verification (if public key provided)
    if author_public_key is not None:
        from core.ee.dryadepkg_format import verify_dryadepkg

        author_valid, _, _, _ = verify_dryadepkg(pkg_bytes, author_public_key)
        if not author_valid:
            raise SecurityError(
                f"Signature verification failed for {pkg_path.name}. "
                "Package may be tampered or signed with a different key."
            )

    # 2. Decrypt and extract payload (entirely in memory)
    file_dict = decrypt_and_extract_payload(pkg_bytes, encryption_key)

    # 3. Derive plugin name from the package filename
    plugin_name = Path(pkg_path).stem  # e.g. "my_plugin" from "my_plugin.dryadepkg"

    # 4. Build in-memory modules from the extracted files
    loaded_modules: dict[str, types.ModuleType] = {}

    # Determine the entry point: prefer __init__.so, fall back to __init__.py
    entry_filename = _pick_entry_point(file_dict)
    entry_bytes = file_dict.get(entry_filename)
    if entry_bytes is None:
        raise ImportError(
            f"No valid entry point found in {pkg_path.name}. "
            f"Expected '__init__.so' or '__init__.py'. Files: {list(file_dict.keys())}"
        )

    # 5. Load .so/.py files in two passes:
    #    Pass 1: Load all non-__init__ files (submodules) and install MemoryModuleLoader.
    #    Pass 2: Load __init__.py last, so intra-plugin imports resolve via the loader.
    top_module: types.ModuleType | None = None
    init_entry: tuple[str, bytes, str] | None = None  # (filename, content, suffix)

    # Pre-register the plugin package namespace so submodule imports resolve.
    pkg_ns_name = f"plugins.{plugin_name}"
    if pkg_ns_name not in sys.modules:
        pkg_ns = types.ModuleType(pkg_ns_name)
        pkg_ns.__path__ = []
        pkg_ns.__package__ = pkg_ns_name
        sys.modules[pkg_ns_name] = pkg_ns

    # Install a live MemoryModuleLoader BEFORE loading any files.
    memory_loader = MemoryModuleLoader(loaded_modules)
    sys.meta_path.insert(0, memory_loader)

    # Pre-register ALL subpackage namespaces found in the archive so that
    # imports like `from plugins.audio.providers import X` resolve even
    # before the subpackage's __init__.py has been exec'd.
    for filename in file_dict:
        fpath = Path(filename)
        if fpath.suffix in (".so", ".py") and len(fpath.parts) > 1:
            # e.g. providers/factory.py -> register plugins.audio.providers
            subpkg = f"plugins.{plugin_name}.{'.'.join(fpath.parts[:-1])}"
            if subpkg not in sys.modules:
                ns = types.ModuleType(subpkg)
                ns.__path__ = []
                ns.__package__ = subpkg
                sys.modules[subpkg] = ns
                loaded_modules[subpkg] = ns
                memory_loader._module_map[subpkg] = ns

    # Sort files: load non-__init__ submodules first, __init__ last.
    # Within submodules, load models/config-like files before others for
    # best-effort dependency ordering.
    init_entry: tuple[str, bytes] | None = None
    submodule_entries: list[tuple[str, bytes]] = []

    for filename, content in file_dict.items():
        suffix = Path(filename).suffix
        if suffix not in (".so", ".py"):
            continue
        fpath = Path(filename)
        # Skip test files — they're not runtime code.
        if fpath.parts[0] == "tests" or "/tests/" in filename:
            continue
        # Only the TOP-LEVEL __init__.py is deferred (plugin entry point).
        # Subpackage __init__ files (e.g. providers/__init__.py) load normally.
        if filename == "__init__.py":
            init_entry = (filename, content)
        else:
            submodule_entries.append((filename, content))

    # Sort: depth-first so subpackage files load before top-level modules that
    # import from them. Within each depth: non-__init__ first, then __init__.
    _priority = {"models": 0, "config": 1, "base": 2, "types": 3, "constants": 4}

    def _sort_key(entry: tuple[str, bytes]) -> tuple[int, int, int, str]:
        fpath = Path(entry[0])
        depth = len(fpath.parts) - 1  # 0 = top-level, 1 = subpackage
        is_init = 1 if fpath.stem == "__init__" else 0
        prio = _priority.get(fpath.stem, 99)
        return (-depth, is_init, prio, entry[0])  # deeper files first

    submodule_entries.sort(key=_sort_key)

    def _filename_to_module_name(filename: str) -> str:
        """Convert tar path like 'providers/whisper.py' to 'plugins.audio.providers.whisper'."""
        fpath = Path(filename)
        parts = list(fpath.parent.parts) + [fpath.stem]
        # Remove leading '.' if present
        parts = [p for p in parts if p != "."]
        if parts == [fpath.stem] and fpath.stem == "__init__":
            return f"plugins.{plugin_name}"
        if fpath.stem == "__init__":
            # Subpackage __init__: providers/__init__.py -> plugins.audio.providers
            return f"plugins.{plugin_name}.{'.'.join(parts[:-1])}"
        return f"plugins.{plugin_name}.{'.'.join(parts)}"

    def _load_and_register(filename: str, content: bytes) -> types.ModuleType | None:
        suffix = Path(filename).suffix
        module_name = _filename_to_module_name(filename)
        is_pkg_init = Path(filename).stem == "__init__"

        # Ensure parent package namespaces exist (e.g. plugins.audio.providers)
        parts = module_name.split(".")
        for i in range(2, len(parts)):
            parent = ".".join(parts[:i])
            if parent not in sys.modules:
                ns = types.ModuleType(parent)
                ns.__path__ = []
                ns.__package__ = parent
                sys.modules[parent] = ns
                loaded_modules[parent] = ns
                memory_loader._module_map[parent] = ns
        mod = None
        if suffix == ".so":
            try:
                mod = load_so_from_memory(content, module_name)
            except ImportError as exc:
                logger.warning("Failed to load .so '%s' from memory: %s", filename, exc)
        elif suffix == ".py":
            mod = _load_py_from_bytes(content, module_name, Path(pkg_path), is_package=is_pkg_init)
        if mod is not None:
            # If this is a subpackage __init__.py, mark it as a package
            if is_pkg_init:
                mod.__package__ = module_name
                mod.__path__ = []
            loaded_modules[module_name] = mod
            sys.modules[module_name] = mod
            memory_loader._module_map[module_name] = mod
        return mod

    # Pass 1: submodules with retry loop — handles arbitrary dependency order.
    # Each successful load registers the module immediately so dependents can
    # import it on the next pass. Converges when no more progress is made.
    remaining = list(submodule_entries)
    max_rounds = len(remaining) + 1
    for _round in range(max_rounds):
        failed: list[tuple[str, bytes]] = []
        for filename, content in remaining:
            try:
                _load_and_register(filename, content)
            except (ImportError, ModuleNotFoundError):
                failed.append((filename, content))
        if not failed:
            break
        if len(failed) == len(remaining):
            # No progress — force-load remaining (will raise on real errors)
            for filename, content in failed:
                _load_and_register(filename, content)
            break
        remaining = failed

    # Pass 2: __init__ (entry point) — all submodules already importable
    if init_entry is not None:
        top_module = _load_and_register(*init_entry)

    if top_module is None:
        raise ImportError(
            f"No top-level module built from {pkg_path.name}. "
            f"Entry point '{entry_filename}' failed to load."
        )

    logger.info(
        "Loaded encrypted plugin '%s' from %s (%d files, all in memory)",
        plugin_name,
        pkg_path.name,
        len(file_dict),
    )
    return top_module

# ── Internal helpers ──────────────────────────────────────────────────────────

def _pick_entry_point(file_dict: dict[str, bytes]) -> str:
    """Choose the best entry point from the extracted file dict.

    Preference order: __init__.so > __init__.py > any .so > any .py
    """
    if "__init__.so" in file_dict:
        return "__init__.so"
    if "__init__.py" in file_dict:
        return "__init__.py"
    for name in file_dict:
        if name.endswith(".so"):
            return name
    for name in file_dict:
        if name.endswith(".py"):
            return name
    return next(iter(file_dict)) if file_dict else ""

def _load_py_from_bytes(
    py_bytes: bytes,
    module_name: str,
    source_path: Path,
    *,
    is_package: bool = False,
) -> types.ModuleType:
    """Compile and execute Python source bytes into a module object in memory.

    The source bytes are compiled to a code object and run via Python's built-in
    exec() with the module's own namespace as the execution context. This is the
    standard mechanism used by importlib itself to execute module code; it is
    intentional here because the input is verified (signature check + AES-GCM
    decryption) before this function is called. No data is written to disk.

    Args:
        py_bytes: Python source code bytes (already decrypted from .dryadepkg).
        module_name: Name to register in sys.modules.
        source_path: Used only for error messages / __file__ attribution.

    Returns:
        New module object with the executed code.
    """
    module = types.ModuleType(module_name)
    module.__file__ = f"<encrypted:{source_path.name}>"
    module.__loader__ = None  # no disk loader
    module.__spec__ = None
    # For packages (__init__.py), __package__ is the module itself.
    # For regular modules, __package__ is the parent package.
    if is_package:
        module.__package__ = module_name
        module.__path__ = []
    else:
        module.__package__ = module_name.rsplit(".", 1)[0] if "." in module_name else module_name

    # Register in sys.modules BEFORE exec so that @dataclass and other
    # metaclass machinery can look up cls.__module__ during class creation.
    sys.modules[module_name] = module

    code = compile(py_bytes, module.__file__, "exec", optimize=0)
    # Execute the compiled code object in the module's namespace.
    # This is equivalent to importlib._bootstrap_external.exec_module() and is
    # the only way to populate module attributes from in-memory source bytes.
    exec(code, module.__dict__)  # noqa: S102  (Python built-in exec, not shell)
    return module

# ── Legacy .pye format support ───────────────────────────────────────────────

ENCRYPTED_PLUGIN_EXTENSION = ".pye"

class EncryptedPluginLoader:
    """Loader for encrypted plugins (.pye files).

    The .pye format is superseded by .dryadepkg (see load_encrypted_plugin above).
    This class is kept for backward compatibility but always returns
    is_available=False in the open-source core.
    """

    def __init__(self):
        self.customer_secret: str | None = None
        self.machine_fingerprint: str | None = None
        self._decryption_cache: dict[str, bytes] = {}

    @property
    def is_available(self) -> bool:
        return bool(self.customer_secret and self.machine_fingerprint)

    def load_encrypted_plugin(self, plugin_path: Path) -> bytes:
        from plugin_manager.security.plugin_encryption import (
            PluginEncryptionError,
            decrypt_plugin_file,
        )

        cache_key = str(plugin_path)
        if cache_key in self._decryption_cache:
            return self._decryption_cache[cache_key]

        if not self.customer_secret:
            raise PluginEncryptionError(
                "Cannot decrypt plugins: no customer secret available. "
                "Set DRYADE_CUSTOMER_SECRET or use a license key with signature."
            )

        plaintext, plugin_name = decrypt_plugin_file(
            plugin_path,
            self.customer_secret,
            self.machine_fingerprint,
        )
        self._decryption_cache[cache_key] = plaintext
        return plaintext

    def clear_cache(self) -> None:
        self._decryption_cache.clear()
