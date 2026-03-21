# Copyright (c) 2025-2026 Dryade SAS
# Licensed under the Dryade Enterprise Edition License. See LICENSE_EE.md.
"""Hardware Identification Utility.

Provides stable machine fingerprint generation for unique hardware identification.
Uses multiple hardware identifiers to create a SHA256 hash that uniquely
identifies this machine across reboots while remaining stable unless
hardware changes significantly.

The fingerprint combines multiple sources:
- CPU information (brand, architecture, count)
- Primary disk device
- MAC address
- Platform information (system, machine, processor)
- Machine UUID (Linux: /etc/machine-id, Windows: Registry)

Exports:
    generate_machine_fingerprint: Generate fingerprint from hardware identifiers
    get_cached_machine_fingerprint: Get cached fingerprint (computed once)
    reset_fingerprint_cache: Clear cache (for testing)
"""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# Cached machine fingerprint (computed once per process)
_cached_fingerprint: str | None = None

def generate_machine_fingerprint(
    include_components: bool = False,
) -> str | tuple[str, dict[str, Any]]:
    """Generate a stable machine fingerprint based on hardware identifiers.

    Uses multiple hardware identifiers to create a SHA256 hash that uniquely
    identifies this machine. The fingerprint remains stable across reboots
    but changes if hardware changes significantly.

    Enhanced fingerprinting combines multiple sources (CPU, disk, MAC, platform, machine_id)
    for improved stability and spoof-resistance.

    Args:
        include_components: If True, returns tuple of (fingerprint, components)
                          for debugging. Default False.

    Returns:
        SHA256 hash of combined hardware identifiers (64 hex characters)
        Or tuple of (hash, components) if include_components=True
    """
    components: dict[str, Any] = {}

    # 1. CPU information (stable across reboots)
    try:
        import cpuinfo as py_cpuinfo

        cpu_info = py_cpuinfo.get_cpu_info()
        components["cpu_brand"] = cpu_info.get("brand_raw", "")
        components["cpu_arch"] = cpu_info.get("arch", "")
        components["cpu_count"] = cpu_info.get("count", 0)
    except Exception as e:
        logger.debug(f"Failed to get CPU info: {e}")
        components["cpu_brand"] = platform.processor()
        components["cpu_arch"] = platform.machine()

    # 2. Primary disk device
    try:
        import psutil

        for partition in psutil.disk_partitions():
            if partition.mountpoint in ["/", "C:\\"]:
                components["disk_device"] = partition.device
                break
    except Exception as e:
        logger.debug(f"Failed to get disk info: {e}")

    # 3. MAC address
    try:
        mac = uuid.getnode()
        components["mac"] = format(mac, "012x")
    except Exception as e:
        logger.debug(f"Failed to get MAC address: {e}")
        components["mac"] = "unknown"

    # 4. Platform information
    components["system"] = platform.system()
    components["machine"] = platform.machine()
    components["processor"] = platform.processor()

    # 5. Machine UUID (Linux: /etc/machine-id, Windows: Registry)
    try:
        if platform.system() == "Linux":
            try:
                with open("/etc/machine-id") as f:
                    components["machine_id"] = f.read().strip()
            except FileNotFoundError:
                try:
                    with open("/var/lib/dbus/machine-id") as f:
                        components["machine_id"] = f.read().strip()
                except FileNotFoundError:
                    pass
        elif platform.system() == "Windows":
            try:
                import winreg

                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    "SOFTWARE\\\\Microsoft\\\\Cryptography",
                    0,
                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                )
                components["machine_id"] = winreg.QueryValueEx(key, "MachineGuid")[0]
                winreg.CloseKey(key)
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"Machine ID not available: {e}")

    # Create deterministic JSON hash (standard format)
    fingerprint_json = json.dumps(components, sort_keys=True)
    fingerprint_hash = hashlib.sha256(fingerprint_json.encode()).hexdigest()

    logger.debug(f"Hardware fingerprint generated with {len(components)} components")

    if include_components:
        return fingerprint_hash, components
    return fingerprint_hash

def get_cached_machine_fingerprint() -> str:
    """Get cached machine fingerprint.

    Fingerprint is calculated once and cached for performance.

    Returns:
        Cached SHA256 fingerprint
    """
    global _cached_fingerprint

    if _cached_fingerprint is None:
        result = generate_machine_fingerprint(include_components=False)
        # Type narrowing: we know it's just the string when include_components=False
        _cached_fingerprint = result if isinstance(result, str) else result[0]

    return _cached_fingerprint

def reset_fingerprint_cache() -> None:
    """Reset fingerprint cache for testing."""
    global _cached_fingerprint
    _cached_fingerprint = None

__all__ = [
    "generate_machine_fingerprint",
    "get_cached_machine_fingerprint",
    "reset_fingerprint_cache",
]
