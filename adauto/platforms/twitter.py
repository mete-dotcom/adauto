"""Twitter/X platform adapter — posts threads via tweepy v4."""
import os
import time
from typing import Optional

try:
    import tweepy
    TWEEPY_OK = True
except ImportError:
    TWEEPY_OK = False

from ..db import add_post, mark_posted, mark_failed
from ..config import Campaign, Platform

TWEET_MAX = 280


def _split_thread(text: str, max_len: int = TWEET_MAX) -> list[str]:
    """Split long text into tweet-sized chunks, breaking at sentence boundaries."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    current = ""
    for sentence in text.replace("\n\n", "\n").split(". "):
        candidate = (current + ". " + sentence).strip() if current else sentence
        if len(candidate) <= max_len - 10:  # -10 for thread numbering
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = sentence[:max_len - 10]
    if current:
        chunks.append(current)

    # Add numbering
    n = len(chunks)
    if n > 1:
        chunks = [f"{i+1}/{n} {c}" for i, c in enumerate(chunks)]
    return chunks


class TwitterPoster:
    """
    Posts to Twitter/X.

    Required env vars:
        TWITTER_API_KEY
        TWITTER_API_SECRET
        TWITTER_ACCESS_TOKEN
        TWITTER_ACCESS_SECRET
        TWITTER_BEARER_TOKEN   (for v2 client)
    """

    def __init__(self):
        if not TWEEPY_OK:
            raise RuntimeError("tweepy not installed — run: pip install tweepy")
        self.client = tweepy.Client(
            bearer_token=os.environ.get("TWITTER_BEARER_TOKEN"),
            consumer_key=os.environ["TWITTER_API_KEY"],
            consumer_secret=os.environ["TWITTER_API_SECRET"],
            access_token=os.environ["TWITTER_ACCESS_TOKEN"],
            access_token_secret=os.environ["TWITTER_ACCESS_SECRET"],
        )

    def post(self, campaign: Campaign, platform: Platform,
             post_data: dict) -> Optional[str]:
        """
        Post a tweet or thread.
        Returns URL of the first tweet.
        """
        post_type = post_data.get("post_type", "showcase")
        body = post_data.get("body", "")
        title = post_data.get("title")

        # Compose tweet text — title + body for short content, body only if fits
        if title and len(title) + len(body) < TWEET_MAX - 2:
            full_text = f"{title}\n{body}"
        else:
            full_text = body

        chunks = _split_thread(full_text)
        post_id = add_post(
            campaign_name=campaign.name,
            platform="twitter",
            post_type=post_type,
            title=title or chunks[0][:100],
            body=full_text,
        )

        try:
            first_id = None
            reply_to = None
            for chunk in chunks:
                kwargs = {"text": chunk}
                if reply_to:
                    kwargs["in_reply_to_tweet_id"] = reply_to
                resp = self.client.create_tweet(**kwargs)
                tweet_id = resp.data["id"]
                if first_id is None:
                    first_id = tweet_id
                reply_to = tweet_id
                time.sleep(1)

            url = f"https://twitter.com/i/web/status/{first_id}"
            mark_posted(post_id, url)
            print(f"[twitter] posted {len(chunks)}-tweet thread: {url}")
            return url
        except Exception as e:
            err = str(e)
            mark_failed(post_id, err)
            print(f"[twitter] FAILED: {err}")
            return None

    def run_campaign(self, campaign: Campaign, posts: list[dict],
                     dry_run: bool = False) -> list[str]:
        plat = campaign.get_platform("twitter")
        if not plat or not plat.enabled:
            print("[twitter] platform disabled or not configured")
            return []

        urls = []
        for post_data in posts[:2]:  # max 2 tweets per run to avoid spam flags
            if dry_run:
                body = post_data.get("body", "")
                chunks = _split_thread(body)
                print(f"[twitter] DRY RUN — {len(chunks)}-tweet thread:")
                for c in chunks:
                    print(f"  [{len(c)}] {c[:80]}...")
                continue
            url = self.post(campaign, plat, post_data)
            if url:
                urls.append(url)
            time.sleep(5)

        return urls
