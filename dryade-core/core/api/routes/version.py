"""Version and compatibility information endpoint.

Used by marketplace and other services to verify
they are compatible with this core instance.
"""

from fastapi import APIRouter

router = APIRouter(tags=["system"])

# Core API version - bump when API contracts change.
# This is separate from the application version.
API_VERSION = "1.0.0"
MIN_PLUGIN_API = "1.0.0"  # Minimum plugin API version supported
MIN_MARKET_API = "1.0.0"  # Minimum marketplace API version supported

@router.get("/api/version")
async def get_version():
    """Return core version and compatibility information.

    Used by:
    - marketplace: checks api_version >= its MIN_CORE_VERSION
    - Health checks and monitoring
    """
    return {
        "api_version": API_VERSION,
        "min_plugin_api": MIN_PLUGIN_API,
        "min_market_api": MIN_MARKET_API,
        "service": "dryade-core",
    }
