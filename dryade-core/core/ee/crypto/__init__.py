# Copyright (c) 2025-2026 Dryade SAS
# Licensed under the Dryade Enterprise Edition License. See LICENSE_EE.md.
"""Enterprise Edition post-quantum cryptography subpackage.

Provides access to PQ crypto via the _load() pattern for .ee.py files.
The pq module is loaded lazily on first attribute access to avoid ImportError
when liboqs-python is not installed (e.g., in dev environments without PQ).

Usage:
    from core.ee.crypto.pq import verify_mldsa65

Or via the package:
    from core.ee.crypto import pq
    pq.verify_mldsa65(...)
"""

import importlib.util
import os
import sys
import types

_dir = os.path.dirname(__file__)

class _LazyPQModule(types.ModuleType):
    """Lazy-loading proxy for pq.ee.py -- defers liboqs import until first use."""

    _real_module = None

    def _load(self):
        if self._real_module is not None:
            return self._real_module

        qualified = "core.ee.crypto.pq"
        spec = importlib.util.spec_from_file_location(qualified, os.path.join(_dir, "pq.ee.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # Replace ourselves in sys.modules with the real module
        sys.modules[qualified] = mod
        _LazyPQModule._real_module = mod
        return mod

    def __getattr__(self, name):
        mod = self._load()
        return getattr(mod, name)

# Register lazy proxy so ``from core.ee.crypto.pq import X`` works
_lazy_pq = _LazyPQModule("core.ee.crypto.pq")
_lazy_pq.__package__ = "core.ee.crypto"
sys.modules["core.ee.crypto.pq"] = _lazy_pq
