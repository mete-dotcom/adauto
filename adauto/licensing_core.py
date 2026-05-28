"""
License key validation core — offline-first, ADTO prefix.
Pattern: ADTO-XXXXX-XXXXX-XXXXX-XXXXX
"""
from __future__ import annotations

import hashlib
import re

KEY_PREFIX   = "ADTO"
KEY_PATTERN  = re.compile(
    r"^ADTO-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}$"
)
SALT         = "adauto-2026-salt"   # keep in sync with Vercel API
FREE_TIER_CAMPAIGNS = 1
FREE_TIER_POSTS_PER_DAY = 3


def is_valid_format(key: str) -> bool:
    return bool(KEY_PATTERN.match(key.upper().strip()))


def key_checksum(key: str) -> str:
    """Compute a deterministic checksum for a key (for offline validation)."""
    normalized = key.upper().strip()
    return hashlib.sha256(f"{SALT}:{normalized}".encode()).hexdigest()[:16]


def is_probably_valid(key: str) -> bool:
    """
    Offline plausibility check.
    Real validation requires a Vercel API call (see license.py).
    """
    return is_valid_format(key)


def tier_from_key(key: str) -> str:
    """
    Derive tier from key prefix hints.
    Full validation is server-side; this is a hint only.
    """
    if not is_valid_format(key):
        return "invalid"
    # First segment after ADTO- encodes tier:
    # Starts with 'P' → pro, 'T' → trial, else → standard
    first_seg = key.upper().split("-")[1]
    if first_seg.startswith("P"):
        return "pro"
    if first_seg.startswith("T"):
        return "trial"
    return "standard"
