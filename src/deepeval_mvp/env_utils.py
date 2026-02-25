"""
env_utils.py — typed helpers for reading environment variables.

All modules in this package import from here.  Never copy-paste these into
individual modules — keep this the single source of truth so that parsing
behaviour (e.g. which strings count as truthy) is consistent across the whole
codebase.
"""
from __future__ import annotations

import os


def env_bool(name: str, default: bool = False) -> bool:
    """Return a boolean from an environment variable.

    Truthy strings: ``1``, ``true``, ``yes``, ``y``, ``on`` (case-insensitive).
    Any other non-empty string is falsy.  Missing variable returns *default*.
    """
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_float(name: str, default: float) -> float:
    """Return a float from an environment variable, falling back to *default*."""
    v = os.getenv(name)
    if v is None or not v.strip():
        return default
    return float(v)


def env_int(name: str, default: int) -> int:
    """Return an int from an environment variable, falling back to *default*."""
    v = os.getenv(name)
    if v is None or not v.strip():
        return default
    return int(v)


def env_csv(name: str, default_csv: str = "") -> list[str]:
    """Return a stripped, non-empty list of strings from a comma-separated env var."""
    raw = os.getenv(name, default_csv) or ""
    return [x.strip() for x in raw.split(",") if x.strip()]
