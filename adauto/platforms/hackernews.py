"""
Hacker News platform handler for adauto.

HN does NOT support automated posting — any automation gets flagged.
This module generates ready-to-submit "Show HN" drafts and outputs them
to the terminal for the user to review and post manually.

adauto generates the content; the human submits.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional

from ..config import Campaign, Platform


@dataclass
class HNDraft:
    title: str
    url: str        # link to submit (site URL or repo)
    comment: str    # optional launch comment (first comment on Show HN)


class HackerNewsPoster:
    """
    Formats posts for Hacker News.

    Posting is manual — call format_draft() to get submission-ready content,
    then open https://news.ycombinator.com/submit and paste.
    """

    SUBMIT_URL = "https://news.ycombinator.com/submit"

    def format_draft(self, camp: Campaign, post: dict) -> HNDraft:
        title = post.get("title") or ""
        body  = post.get("body") or ""
        ptype = post.get("post_type", "showcase")

        # HN title rules: no exclamation marks, no clickbait, factual
        # Remove trailing punctuation and emoji from LLM output
        title = title.rstrip("!.").strip()
        if not title:
            title = f"Show HN: {camp.product} — {camp.tagline[:60]}"

        # "Show HN" prefix for launches, plain title for discussions
        if ptype in ("showcase",) and not title.lower().startswith("show hn"):
            title = f"Show HN: {title}"
        elif ptype == "question" and not title.lower().startswith("ask hn"):
            title = f"Ask HN: {title}"

        # First comment = expanded context (HN convention)
        # Keep under ~600 chars — HN readers are busy
        comment = body[:600].strip()
        if len(body) > 600:
            comment += "\n\n(more at the link above)"

        return HNDraft(title=title, url=camp.site_url, comment=comment)

    def post(self, camp: Campaign, plat: Platform, post: dict) -> Optional[str]:
        """
        'Post' to HN = print formatted draft to terminal.
        Returns None (can't verify a URL until the user submits).
        """
        draft = self.format_draft(camp, post)

        print(f"\n{'─'*60}")
        print(f"  HN SUBMISSION DRAFT  ({camp.product})")
        print(f"{'─'*60}")
        print(f"  Submit at: {self.SUBMIT_URL}")
        print()
        print(f"  TITLE  : {draft.title}")
        print(f"  URL    : {draft.url}")
        print()
        print(f"  FIRST COMMENT (paste after submitting):")
        print()
        for ln in draft.comment.splitlines():
            print(f"    {ln}")
        print(f"{'─'*60}\n")
        sys.stdout.flush()
        return None   # can't return a URL — manual step

    def run_campaign(self, camp: Campaign, posts: list[dict]) -> None:
        """Print drafts for all posts."""
        for p in posts:
            self.post(camp, camp.get_platform("hackernews"), p)
        print(
            f"\n  [{camp.name}/hackernews] {len(posts)} draft(s) printed above.\n"
            f"  Submit each at: {self.SUBMIT_URL}\n"
            f"  Tip: space submissions at least 48h apart to avoid flag risk."
        )
