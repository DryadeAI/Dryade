"""Timezone-aware UTC datetime utilities.

Replaces deprecated datetime.utcnow() (Python 3.12+) with
timezone-aware equivalents.
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware datetime.

    This replaces ``datetime.utcnow()`` which is deprecated in Python 3.12
    because it returns naive datetimes that can cause timezone bugs.
    """
    return datetime.now(timezone.utc)
