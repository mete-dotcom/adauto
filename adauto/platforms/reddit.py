"""Reddit platform adapter — posts via PRAW, respects cooldown."""
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

try:
    import praw
    PRAW_OK = True
except ImportError:
    PRAW_OK = False

from ..db import add_post, mark_posted, mark_failed, kv_get, kv_set
from ..config import Campaign, Platform


class RedditPoster:
    """
    Posts to Reddit subreddits.

    Required env vars:
        REDDIT_CLIENT_ID
        REDDIT_CLIENT_SECRET
        REDDIT_USERNAME
        REDDIT_PASSWORD
        REDDIT_USER_AGENT   (optional, default: "adauto/0.1")
    """

    def __init__(self):
        if not PRAW_OK:
            raise RuntimeError("praw not installed — run: pip install praw")
        self.reddit = praw.Reddit(
            client_id=os.environ["REDDIT_CLIENT_ID"],
            client_secret=os.environ["REDDIT_CLIENT_SECRET"],
            username=os.environ["REDDIT_USERNAME"],
            password=os.environ["REDDIT_PASSWORD"],
            user_agent=os.environ.get("REDDIT_USER_AGENT", "adauto/0.1 by adauto"),
        )

    def _cooldown_key(self, campaign_name: str, subreddit: str) -> str:
        return f"reddit_cooldown:{campaign_name}:{subreddit}"

    def _is_on_cooldown(self, campaign_name: str, subreddit: str,
                         cooldown_hours: int) -> bool:
        key = self._cooldown_key(campaign_name, subreddit)
        last_str = kv_get(key)
        if not last_str:
            return False
        last = datetime.fromisoformat(last_str)
        elapsed = datetime.now(timezone.utc) - last
        return elapsed < timedelta(hours=cooldown_hours)

    def _record_post(self, campaign_name: str, subreddit: str) -> None:
        key = self._cooldown_key(campaign_name, subreddit)
        kv_set(key, datetime.now(timezone.utc).isoformat())

    def post(self, campaign: Campaign, platform: Platform,
             post_data: dict, subreddit: str) -> Optional[str]:
        """
        Submit one post to a subreddit.

        post_data: dict with 'title' and 'body' keys (from generator)
        Returns: submission URL or None on failure
        """
        post_type = post_data.get("post_type", "showcase")

        # Cooldown check
        if self._is_on_cooldown(campaign.name, subreddit, platform.cooldown_hours):
            print(f"[reddit] skip r/{subreddit} — on cooldown")
            return None

        title = post_data.get("title") or f"{campaign.product}: {campaign.tagline}"
        body = post_data.get("body", "")

        # Track in DB
        post_id = add_post(
            campaign_name=campaign.name,
            platform="reddit",
            post_type=post_type,
            title=title,
            body=body,
        )

        try:
            sub = self.reddit.subreddit(subreddit)
            # Determine post format: text if body > 280 chars, otherwise link
            if len(body) > 100:
                submission = sub.submit(title=title, selftext=body)
            else:
                # Short body → try link post to repo
                submission = sub.submit(title=title, url=campaign.repo_url)

            url = f"https://reddit.com{submission.permalink}"
            mark_posted(post_id, url)
            self._record_post(campaign.name, subreddit)
            print(f"[reddit] posted to r/{subreddit}: {url}")
            return url

        except Exception as e:
            err = str(e)
            mark_failed(post_id, err)
            print(f"[reddit] FAILED r/{subreddit}: {err}")
            return None

    def reply(self, thread_url: str, body: str) -> Optional[str]:
        """
        Post a comment reply to an existing Reddit thread.
        Used by the pain-responder to answer threads where someone needs help.

        thread_url: full reddit URL (e.g. https://reddit.com/r/Python/comments/...)
        Returns: comment permalink or None on failure.
        """
        try:
            # Extract submission id from URL
            import re as _re
            m = _re.search(r"comments/([a-z0-9]+)", thread_url)
            if not m:
                print(f"[reddit] reply: cannot parse submission id from {thread_url}")
                return None
            submission = self.reddit.submission(id=m.group(1))
            comment = submission.reply(body)
            url = f"https://reddit.com{comment.permalink}"
            print(f"[reddit] replied: {url}")
            return url
        except Exception as e:
            print(f"[reddit] reply FAILED: {e}")
            return None

    def run_campaign(self, campaign: Campaign, posts: list[dict],
                     dry_run: bool = False) -> list[str]:
        """
        Distribute generated posts across subreddits.
        One post per subreddit (respects cooldown).
        Returns list of posted URLs.
        """
        plat = campaign.get_platform("reddit")
        if not plat or not plat.enabled:
            print("[reddit] platform disabled or not configured")
            return []

        subreddits = plat.subreddits
        if not subreddits:
            print("[reddit] no subreddits configured")
            return []

        urls = []
        post_idx = 0
        for sub in subreddits:
            if post_idx >= len(posts):
                print("[reddit] ran out of generated posts")
                break
            post_data = posts[post_idx]
            if dry_run:
                print(f"[reddit] DRY RUN — would post to r/{sub}: {post_data.get('title', '')[:60]}")
                post_idx += 1
                continue
            url = self.post(campaign, plat, post_data, sub)
            if url:
                urls.append(url)
                post_idx += 1
            time.sleep(2)  # small delay between submissions

        return urls
