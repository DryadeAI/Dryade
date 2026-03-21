# Copyright (c) 2025-2026 Dryade SAS
# Licensed under the Dryade Enterprise Edition License. See LICENSE_EE.md.
"""Dryade Enterprise Edition components.

Files in this directory require an active Dryade subscription for
production use. See https://dryade.ai/pricing for details.

These files are licensed under the Dryade Source Use License (DSUL)
Enterprise Addendum. See LICENSE-EE.md in the repository root.

This module provides an import facade for .ee.py files, which cannot
be imported directly via Python's standard import system due to the dot
in their file extension. Use this package to access EE modules:

    from core.ee import encrypted_loader
    from core.ee import fingerprint
    from core.ee import internal_api
    from core.ee import plugin_loader

Or access exported symbols directly:

    from core.ee import load_encrypted_plugin, SecurityError
    from core.ee import EncryptedPluginLoader, ENCRYPTED_PLUGIN_EXTENSION
    from core.ee import generate_machine_fingerprint, get_cached_machine_fingerprint
    from core.ee import start_internal_api, set_hot_reload_callback
    from core.ee import load_plugin
"""

import importlib.util
import os
import sys

_dir = os.path.dirname(__file__)

def _load(name: str, filename: str):
    """Load a .ee.py module by filename using importlib.

    Registers the module in sys.modules as ``core.ee.<name>`` so that
    ``from core.ee.<name> import symbol`` works via Python's normal
    import machinery.
    """
    qualified = f"core.ee.{name}"
    spec = importlib.util.spec_from_file_location(qualified, os.path.join(_dir, filename))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[qualified] = mod
    spec.loader.exec_module(mod)
    return mod

# Load enterprise edition modules
# Order matters: modules with dependencies must be loaded after their deps.
# Tier 1: no internal EE dependencies
encrypted_loader = _load("encrypted_loader", "encrypted_loader.ee.py")
fingerprint = _load("fingerprint", "fingerprint.ee.py")
plugin_loader = _load("plugin_loader", "plugin_loader.ee.py")
integrity_ee = _load("integrity_ee", "integrity.ee.py")
heartbeat_ee = _load("heartbeat_ee", "heartbeat.ee.py")

# Phase 178.1: New EE modules (plugin binary handling -- depend on crypto.pq)
dryadepkg_format = _load("dryadepkg_format", "dryadepkg_format.ee.py")
encrypted_bridge = _load("encrypted_bridge", "encrypted_bridge.ee.py")

# Phase 196.1: Tier 2+3 EE modules (allowlist depends on crypto.pq, watchdog depends on allowlist)
allowlist_ee = _load("allowlist_ee", "allowlist.ee.py")
allowlist_watchdog_ee = _load("allowlist_watchdog_ee", "allowlist_watchdog.ee.py")

# Plugin security (allowlist gate, hash verification, encryption keys, UI bundle check)
# Depends on allowlist_ee for get_allowed_plugins/get_plugin_hashes.
plugin_security_ee = _load("plugin_security_ee", "plugin_security.ee.py")

# Plugin config store (persistent plugin configuration)
plugin_config_store_ee = _load("plugin_config_store_ee", "plugin_config_store.ee.py")

# internal_api depends on allowlist_ee (top-level import), must load after
internal_api = _load("internal_api", "internal_api.ee.py")

# Re-export commonly used symbols for convenience
# From encrypted_loader (dryadepkg + legacy .pye)
EncryptedPluginLoader = encrypted_loader.EncryptedPluginLoader
ENCRYPTED_PLUGIN_EXTENSION = encrypted_loader.ENCRYPTED_PLUGIN_EXTENSION
load_encrypted_plugin = encrypted_loader.load_encrypted_plugin
SecurityError = encrypted_loader.SecurityError
MemoryModuleLoader = encrypted_loader.MemoryModuleLoader
load_so_from_memory = encrypted_loader.load_so_from_memory
decrypt_and_extract_payload = encrypted_loader.decrypt_and_extract_payload

# From dryadepkg_format
build_dryadepkg = dryadepkg_format.build_dryadepkg
read_dryadepkg_manifest = dryadepkg_format.read_dryadepkg_manifest
verify_dryadepkg = dryadepkg_format.verify_dryadepkg
decrypt_dryadepkg_payload = dryadepkg_format.decrypt_dryadepkg_payload

# From encrypted_bridge
EncryptedPluginBridge = encrypted_bridge.EncryptedPluginBridge
encrypt_route_path = encrypted_bridge.encrypt_route_path
encrypt_response = encrypted_bridge.encrypt_response
decrypt_response = encrypted_bridge.decrypt_response
derive_session_key = encrypted_bridge.derive_session_key
RouteNotFoundError = encrypted_bridge.RouteNotFoundError

# From fingerprint
generate_machine_fingerprint = fingerprint.generate_machine_fingerprint
get_cached_machine_fingerprint = fingerprint.get_cached_machine_fingerprint
reset_fingerprint_cache = fingerprint.reset_fingerprint_cache

# From internal_api
start_internal_api = internal_api.start_internal_api
stop_internal_api = internal_api.stop_internal_api
set_hot_reload_callback = internal_api.set_hot_reload_callback
internal_app = internal_api.internal_app

# From plugin_loader
load_plugin = plugin_loader.load_plugin

# From integrity_ee
check_core_integrity = integrity_ee.check_core_integrity
log_integrity_at_startup = integrity_ee.log_integrity_at_startup

# From heartbeat_ee
start_heartbeat = heartbeat_ee.start_heartbeat
stop_heartbeat = heartbeat_ee.stop_heartbeat
is_revoked = heartbeat_ee.is_revoked

# From allowlist_ee
get_allowed_plugins = allowlist_ee.get_allowed_plugins
get_tier_metadata = allowlist_ee.get_tier_metadata
get_plugin_hashes = allowlist_ee.get_plugin_hashes
get_allowlist_path = allowlist_ee.get_allowlist_path
get_current_allowlist_data = allowlist_ee.get_current_allowlist_data
is_allowlist_expired = allowlist_ee.is_allowlist_expired
verify_and_load_allowlist = allowlist_ee.verify_and_load_allowlist
write_allowlist_file = allowlist_ee.write_allowlist_file
AllowlistResult = allowlist_ee.AllowlistResult
TierMetadata = allowlist_ee.TierMetadata

# From plugin_security_ee
validate_before_load = plugin_security_ee.validate_before_load
reload_allowlist = plugin_security_ee.reload_allowlist
verify_plugin_hash = plugin_security_ee.verify_plugin_hash
verify_dryadepkg_hash = plugin_security_ee.verify_dryadepkg_hash

# From plugin_config_store_ee
PluginConfigStore = plugin_config_store_ee.PluginConfigStore

# From allowlist_watchdog_ee
AllowlistWatchdog = allowlist_watchdog_ee.AllowlistWatchdog
get_allowlist_watchdog = allowlist_watchdog_ee.get_allowlist_watchdog

__all__ = [
    # Submodules
    "encrypted_loader",
    "dryadepkg_format",
    "encrypted_bridge",
    "fingerprint",
    "internal_api",
    "plugin_loader",
    # encrypted_loader exports
    "EncryptedPluginLoader",
    "ENCRYPTED_PLUGIN_EXTENSION",
    "load_encrypted_plugin",
    "SecurityError",
    "MemoryModuleLoader",
    "load_so_from_memory",
    "decrypt_and_extract_payload",
    # dryadepkg_format exports
    "build_dryadepkg",
    "read_dryadepkg_manifest",
    "verify_dryadepkg",
    "decrypt_dryadepkg_payload",
    # encrypted_bridge exports
    "EncryptedPluginBridge",
    "encrypt_route_path",
    "encrypt_response",
    "decrypt_response",
    "derive_session_key",
    "RouteNotFoundError",
    # fingerprint exports
    "generate_machine_fingerprint",
    "get_cached_machine_fingerprint",
    "reset_fingerprint_cache",
    # internal_api exports
    "start_internal_api",
    "stop_internal_api",
    "set_hot_reload_callback",
    "internal_app",
    # plugin_loader exports
    "load_plugin",
    # integrity_ee exports
    "integrity_ee",
    "check_core_integrity",
    "log_integrity_at_startup",
    # heartbeat_ee exports
    "heartbeat_ee",
    "start_heartbeat",
    "stop_heartbeat",
    "is_revoked",
    # allowlist_ee exports
    "allowlist_ee",
    "get_allowed_plugins",
    "get_tier_metadata",
    "get_plugin_hashes",
    "get_allowlist_path",
    "get_current_allowlist_data",
    "is_allowlist_expired",
    "verify_and_load_allowlist",
    "write_allowlist_file",
    "AllowlistResult",
    "TierMetadata",
    # plugin_security_ee exports
    "plugin_security_ee",
    "validate_before_load",
    "reload_allowlist",
    "verify_plugin_hash",
    "verify_dryadepkg_hash",
    # plugin_config_store_ee exports
    "plugin_config_store_ee",
    "PluginConfigStore",
    # allowlist_watchdog_ee exports
    "allowlist_watchdog_ee",
    "AllowlistWatchdog",
    "get_allowlist_watchdog",
]
