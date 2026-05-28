"""dev.to platform adapter — publishes articles via dev.to API v1."""
import os
from typing import Optional

try:
    import requests as _req
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

from ..db import add_post, mark_posted, mark_failed
from ..config import Campaign, Platform

DEVTO_API = "https://dev.to/api"


class DevtoPoster:
    """
    Publishes articles to dev.to.

    Required env var:
        DEVTO_API_KEY  — from https://dev.to/settings/extensions
    """

    def __init__(self):
        self.api_key = os.environ.get("DEVTO_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("DEVTO_API_KEY not set")
        self.headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }

    def post(self, campaign: Campaign, platform: Platform,
             post_data: dict, published: bool = True) -> Optional[str]:
        """
        Create a dev.to article.
        Returns article URL or None.
        """
        post_type = post_data.get("post_type", "showcase")
        title = post_data.get("title") or f"{campaign.product}: {campaign.tagline}"
        body = post_data.get("body", "")
        tags = post_data.get("tags", [])[:4]  # dev.to max 4 tags

        # Prepend canonical link and install instruction if not present
        if campaign.repo_url not in body:
            footer = f"\n\n---\n\n**Install**: `{campaign.install_cmd}`  \n**Repo**: {campaign.repo_url}  \n**Site**: {campaign.site_url}"
            body += footer

        post_id = add_post(
            campaign_name=campaign.name,
            platform="devto",
            post_type=post_type,
            title=title,
            body=body,
        )

        payload = {
            "article": {
                "title": title,
                "body_markdown": body,
                "published": published,
                "tags": tags,
                "canonical_url": campaign.site_url,
            }
        }

        try:
            resp = _req.post(f"{DEVTO_API}/articles", json=payload,
                             headers=self.headers, timeout=30)
            resp.raise_for_status()
            article = resp.json()
            url = article.get("url") or f"https://dev.to/api/articles/{article['id']}"
            mark_posted(post_id, url)
            print(f"[devto] published: {url}")
            return url
        except Exception as e:
            err = str(e)
            mark_failed(post_id, err)
            print(f"[devto] FAILED: {err}")
            return None

    def run_campaign(self, campaign: Campaign, posts: list[dict],
                     dry_run: bool = False) -> list[str]:
        plat = campaign.get_platform("devto")
        if not plat or not plat.enabled:
            print("[devto] platform disabled or not configured")
            return []

        urls = []
        for post_data in posts[:3]:  # max 3 articles per run
            if dry_run:
                print(f"[devto] DRY RUN — would publish: {post_data.get('title', '')[:60]}")
                continue
            url = self.post(campaign, plat, post_data)
            if url:
                urls.append(url)

        return urls
