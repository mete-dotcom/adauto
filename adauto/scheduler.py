"""Scheduler — decides which campaigns/platforms to run based on posts_per_day."""
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from .db import kv_get, kv_set, get_stats
from .config import Campaign, Platform


def _last_run_key(campaign_name: str, platform_name: str) -> str:
    return f"last_run:{campaign_name}:{platform_name}"


def get_last_run(campaign_name: str, platform_name: str) -> Optional[datetime]:
    val = kv_get(_last_run_key(campaign_name, platform_name))
    if val:
        return datetime.fromisoformat(val)
    return None


def record_run(campaign_name: str, platform_name: str) -> None:
    kv_set(_last_run_key(campaign_name, platform_name),
           datetime.now(timezone.utc).isoformat())


def is_due(campaign: Campaign, platform: Platform) -> bool:
    """Return True if this platform is due for a new post."""
    if not platform.enabled or not campaign.enabled:
        return False

    last = get_last_run(campaign.name, platform.name)
    if last is None:
        return True  # never run → always due

    interval_hours = 24.0 / max(platform.posts_per_day, 0.1)
    interval = timedelta(hours=interval_hours)
    now = datetime.now(timezone.utc)
    # Make last timezone-aware if naive
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (now - last) >= interval


def due_platforms(campaign: Campaign) -> list[Platform]:
    """Return list of platforms that are due for a post right now."""
    return [p for p in campaign.platforms if is_due(campaign, p)]
