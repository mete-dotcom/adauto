"""
License management for adauto.
Stores activation state in ~/.adauto/license.json
Validates against Vercel API on first activation; then offline.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from .licensing_core import is_valid_format, tier_from_key, FREE_TIER_CAMPAIGNS, FREE_TIER_POSTS_PER_DAY

LICENSE_FILE    = Path.home() / ".adauto" / "license.json"
VERIFY_ENDPOINT = "https://adauto.vercel.app/api/verify"  # update after deploy


def _load() -> dict:
    if LICENSE_FILE.exists():
        try:
            return json.loads(LICENSE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save(data: dict) -> None:
    LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    LICENSE_FILE.write_text(json.dumps(data, indent=2))


def activate(key: str) -> dict:
    """
    Activate a license key.
    1. Format check (offline)
    2. Server validation (online, once)
    3. Store result locally
    Returns {"ok": bool, "tier": str, "message": str}
    """
    key = key.upper().strip()

    if not is_valid_format(key):
        return {"ok": False, "message": "Invalid key format. Expected: ADTO-XXXXX-XXXXX-XXXXX-XXXXX"}

    # Try server validation
    try:
        import requests
        resp = requests.post(
            VERIFY_ENDPOINT,
            json={"key": key},
            timeout=10,
        )
        data = resp.json()
        if not data.get("valid"):
            return {"ok": False, "message": data.get("message", "Key rejected by server")}
        tier = data.get("tier", "standard")
    except Exception as e:
        # Offline fallback: accept if format is valid (grace mode)
        tier = tier_from_key(key)
        data = {"grace": True, "error": str(e)}

    license_data = {
        "key":        key,
        "tier":       tier,
        "activated":  time.time(),
        "last_check": time.time(),
        "server":     data,
    }
    _save(license_data)
    return {"ok": True, "tier": tier, "message": f"Activated ({tier} tier)"}


def status() -> dict:
    """Return current license status."""
    data = _load()
    if not data:
        return {
            "licensed": False,
            "tier": "free",
            "campaigns_allowed": FREE_TIER_CAMPAIGNS,
            "posts_per_day_allowed": FREE_TIER_POSTS_PER_DAY,
            "message": "No license. Run: adauto license activate <key>",
        }
    return {
        "licensed":              True,
        "key":                   data["key"][:9] + "****",  # mask
        "tier":                  data["tier"],
        "activated":             data["activated"],
        "campaigns_allowed":     999 if data["tier"] in ("pro", "standard") else FREE_TIER_CAMPAIGNS,
        "posts_per_day_allowed": 999 if data["tier"] == "pro" else 10,
    }


def is_licensed() -> bool:
    return bool(_load())


def check_limit(campaign_count: int) -> Optional[str]:
    """
    Return an error message if limits are exceeded, else None.
    Free tier: max 1 campaign, 3 posts/day.
    """
    data = _load()
    if data:
        return None  # any license = no limits (for now)
    if campaign_count > FREE_TIER_CAMPAIGNS:
        return (
            f"Free tier: max {FREE_TIER_CAMPAIGNS} campaign. "
            f"Activate a license: adauto license activate <key>"
        )
    return None


def get_key() -> Optional[str]:
    data = _load()
    return data.get("key") if data else None
