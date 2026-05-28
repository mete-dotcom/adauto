"""adauto CLI — multi-platform developer marketing automation."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import click

from . import __version__
from .db import (
    init_db, get_stats, get_pending_approval, get_approved,
    approve_post, skip_post, update_post_body,
)
from .config import load_campaign, list_campaigns, CAMPAIGNS_DIR
from .server import DEFAULT_PORT, DEFAULT_IDLE_TIMEOUT


@click.group()
@click.version_option(__version__)
def cli():
    """adauto — automated developer marketing with human approval."""
    init_db()


# ── adauto serve ──────────────────────────────────────────────────────────────

@cli.command()
@click.option("--port", "-p", default=DEFAULT_PORT, show_default=True)
@click.option("--host", default="0.0.0.0", show_default=True)
@click.option("--idle-timeout", default=DEFAULT_IDLE_TIMEOUT, show_default=True,
              help="Auto-shutdown after N idle seconds (OS service restarts)")
@click.option("--ds-url", default="http://localhost:8765", show_default=True,
              help="deepstrain URL for content generation")
@click.option("--no-mdns", is_flag=True, default=False,
              help="Disable mDNS broadcasting")
def serve(port, host, idle_timeout, ds_url, no_mdns):
    """Start the adauto HTTP server (GET /, /exec, /eval, /approve)."""
    from .server import run_server

    click.echo(f"[adauto] v{__version__}")
    click.echo(f"[adauto] HTTP server: http://{host}:{port}/")
    click.echo(f"[adauto] deepstrain : {ds_url}")
    click.echo(f"[adauto] idle timeout: {idle_timeout}s")

    _beacon = None
    if not no_mdns:
        try:
            from .discover import start_beacon
            _beacon = start_beacon(port)
            click.echo(f"[adauto] mDNS: adauto.local:{port}")
        except Exception:
            pass

    run_server(host=host, port=port, idle_timeout=idle_timeout, ds_url=ds_url)


# ── adauto service ────────────────────────────────────────────────────────────

@cli.command()
@click.argument("action", type=click.Choice(
    ["install", "uninstall", "start", "stop", "status"], case_sensitive=False
))
def service(action):
    """Manage adauto OS service (auto-starts on boot).

    \b
    adauto service install   — register as OS service
    adauto service start     — start now
    adauto service stop      — stop
    adauto service status    — check if running
    adauto service uninstall — remove
    """
    from .service import service_cmd
    service_cmd(action.lower())


# ── adauto init ───────────────────────────────────────────────────────────────

@cli.command()
def init():
    """Initialize adauto config directories and database."""
    from .config import CONFIG_DIR
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CAMPAIGNS_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    click.echo(f"[adauto] initialized at {CONFIG_DIR}")
    click.echo(f"[adauto] campaign configs: {CAMPAIGNS_DIR}")
    click.echo("[adauto] next: copy a campaign TOML (see campaigns/ in repo)")


# ── adauto campaigns ──────────────────────────────────────────────────────────

@cli.command()
def campaigns():
    """List configured campaigns."""
    names = list_campaigns()
    if not names:
        click.echo(f"No campaigns found. Add .toml files to {CAMPAIGNS_DIR}")
        return
    for n in names:
        camp = load_campaign(n)
        status = "✓" if (camp and camp.enabled) else "✗"
        plats  = ", ".join(p.name for p in camp.platforms) if camp else "?"
        click.echo(f"  {status}  {n:20s}  [{plats}]")


# ── adauto generate ───────────────────────────────────────────────────────────

@cli.command()
@click.argument("campaign_name")
@click.option("--platform", "-p", default=None)
@click.option("--count", "-n", default=3, show_default=True)
@click.option("--post-type", "-t", default=None)
@click.option("--ds-url", default="http://localhost:8765")
def generate(campaign_name, platform, count, post_type, ds_url):
    """Generate posts and queue for approval (they do NOT post automatically)."""
    camp = load_campaign(campaign_name)
    if not camp:
        click.echo(f"Campaign not found: {campaign_name}", err=True); sys.exit(1)

    platforms = [p for p in camp.platforms if p.enabled]
    if platform:
        platforms = [p for p in platforms if p.name == platform]
    if not platforms:
        click.echo("No enabled platforms."); sys.exit(1)

    from .generator import generate_post
    from .db import add_post
    from .analytics import best_post_type

    total = 0
    for plat in platforms:
        for i in range(count):
            ptype = post_type or best_post_type(camp.name, plat.name,
                                                fallback=plat.post_types[i % len(plat.post_types)])
            click.echo(f"[generate] {plat.name}/{ptype} ({i+1}/{count})...", nl=False)
            t0 = time.monotonic()
            post = generate_post(camp, plat.name, ptype, ds_url=ds_url or camp.deepstrain_url)
            elapsed = time.monotonic() - t0
            if post:
                pid = add_post(
                    campaign_name=campaign_name,
                    platform=plat.name,
                    post_type=ptype,
                    title=post.get("title", ""),
                    body=post.get("body", ""),
                )
                click.echo(f" ✓ #{pid} ({elapsed:.1f}s, {len(post.get('body',''))} chars)")
                total += 1
            else:
                click.echo(f" ✗ failed")

    click.echo(f"\n[generate] {total} post(s) queued for review.")
    click.echo("Run `adauto review` to approve/skip before posting.")


# ── adauto review ─────────────────────────────────────────────────────────────

@cli.command()
@click.option("--campaign", "-c", default=None)
@click.option("--platform", "-p", default=None)
@click.option("--approve-all", is_flag=True, default=False,
              help="Approve all pending posts without interactive review")
def review(campaign, platform, approve_all):
    """Review pending posts and approve/skip each one before posting.

    This is the mandatory approval step — nothing posts without your OK.
    """
    posts = get_pending_approval(campaign_name=campaign, platform=platform)
    if not posts:
        click.echo("No posts pending approval.")
        return

    click.echo(f"\n{'='*60}")
    click.echo(f"  {len(posts)} post(s) pending approval")
    click.echo(f"{'='*60}\n")

    if approve_all:
        for p in posts:
            approve_post(p["id"])
        click.echo(f"✓ Approved all {len(posts)} posts.")
        click.echo("Run `adauto post` to publish approved posts.")
        return

    approved_count = 0
    skipped_count  = 0

    for i, p in enumerate(posts, 1):
        click.echo(f"[{i}/{len(posts)}] Campaign: {p['campaign_name']}  Platform: {p['platform']}  Type: {p['post_type']}")
        click.echo(f"ID: #{p['id']}")
        if p.get("title"):
            click.echo(f"\nTITLE:\n{p['title']}")
        click.echo(f"\nBODY ({len(p.get('body',''))} chars):")
        click.echo("─" * 50)
        body = p.get("body", "")
        # Show first 800 chars
        click.echo(body[:800])
        if len(body) > 800:
            click.echo(f"\n... [{len(body)-800} more chars hidden]")
        click.echo("─" * 50)

        while True:
            choice = click.prompt(
                "\n[a]pprove  [s]kip  [e]dit  [v]iew full  [q]uit review",
                default="a",
            ).strip().lower()

            if choice in ("a", "approve"):
                approve_post(p["id"])
                click.echo("✓ Approved")
                approved_count += 1
                break
            elif choice in ("s", "skip"):
                skip_post(p["id"])
                click.echo("✗ Skipped")
                skipped_count += 1
                break
            elif choice in ("v", "view"):
                click.echo("\n" + "="*60)
                click.echo(body)
                click.echo("="*60)
            elif choice in ("e", "edit"):
                new_title = click.prompt("New title (enter to keep)", default=p.get("title",""))
                click.echo("Paste new body (end with a line containing only '---'):")
                lines = []
                while True:
                    ln = input()
                    if ln == "---":
                        break
                    lines.append(ln)
                new_body = "\n".join(lines) if lines else body
                update_post_body(p["id"], new_title, new_body)
                approve_post(p["id"])
                click.echo("✓ Edited + Approved")
                approved_count += 1
                break
            elif choice in ("q", "quit"):
                click.echo(f"\nReview paused. {approved_count} approved, {skipped_count} skipped.")
                return
            else:
                click.echo("Invalid choice. Use a/s/e/v/q")

        click.echo()

    click.echo(f"\n{'='*60}")
    click.echo(f"Review complete: {approved_count} approved, {skipped_count} skipped")
    if approved_count > 0:
        click.echo("Run `adauto post` to publish approved posts.")
    click.echo("="*60)


# ── adauto post ───────────────────────────────────────────────────────────────

@cli.command()
@click.argument("campaign_name")
@click.option("--platform", "-p", default=None)
@click.option("--dry-run", is_flag=True, default=False)
def post(campaign_name, platform, dry_run):
    """Publish all APPROVED posts for a campaign.

    Only posts that have been approved via `adauto review` will be published.
    """
    camp = load_campaign(campaign_name)
    if not camp:
        click.echo(f"Campaign not found: {campaign_name}", err=True); sys.exit(1)

    approved = get_approved(platform=platform)
    camp_approved = [p for p in approved if p["campaign_name"] == campaign_name]

    if not camp_approved:
        click.echo(f"No approved posts for '{campaign_name}'. Run `adauto generate` then `adauto review`.")
        return

    if dry_run:
        click.echo(f"[dry-run] Would publish {len(camp_approved)} post(s):")
        for p in camp_approved:
            click.echo(f"  #{p['id']} [{p['platform']}] {p['post_type']} — {(p.get('title') or p.get('body',''))[:60]}")
        return

    click.echo(f"Publishing {len(camp_approved)} approved post(s)...")

    from .scheduler import record_run

    by_platform: dict = {}
    for p in camp_approved:
        by_platform.setdefault(p["platform"], []).append(p)

    for plat_name, posts in by_platform.items():
        plat = camp.get_platform(plat_name)
        if not plat:
            continue
        try:
            if plat_name == "reddit":
                from .platforms.reddit import RedditPoster
                poster = RedditPoster()
                for p in posts:
                    subs = plat.subreddits or ["programming"]
                    url = poster.post(camp, plat, p, subreddit=subs[0])
                    click.echo(f"  #{p['id']} → {url or 'FAILED'}")
            elif plat_name == "devto":
                from .platforms.devto import DevtoPoster
                poster = DevtoPoster()
                poster.run_campaign(camp, posts)
            elif plat_name == "twitter":
                from .platforms.twitter import TwitterPoster
                poster = TwitterPoster()
                poster.run_campaign(camp, posts)
        except RuntimeError as e:
            click.echo(f"  [{plat_name}] skipped — {e}")

        record_run(campaign_name, plat_name)


# ── adauto run (full automated loop) ─────────────────────────────────────────

@cli.command()
@click.option("--campaign", "-c", default=None)
@click.option("--platform", "-p", default=None)
@click.option("--ds-url", default="http://localhost:8765")
@click.option("--dry-run", is_flag=True)
@click.option("--once", is_flag=True, help="Generate + queue, then stop (no posting)")
def run(campaign, platform, ds_url, dry_run, once):
    """Full automation loop: generate → print for review → (if approved) post.

    Posts are NEVER published automatically without approval.
    Use --once to generate and queue posts, then review with `adauto review`.
    """
    names = [campaign] if campaign else list_campaigns()
    from .scheduler import due_platforms
    from .generator import generate_batch
    from .db import add_post

    for name in names:
        camp = load_campaign(name)
        if not camp or not camp.enabled:
            continue
        due = due_platforms(camp)
        if not due:
            click.echo(f"[run] {name} — nothing due")
            continue

        for plat in due:
            if platform and plat.name != platform:
                continue
            click.echo(f"[run] {name}/{plat.name} — generating {len(plat.subreddits or [1])} posts...")
            posts = generate_batch(camp, plat.name,
                                   count=max(1, len(plat.subreddits or [1])),
                                   ds_url=ds_url or camp.deepstrain_url)
            for p in posts:
                pid = add_post(
                    campaign_name=name,
                    platform=plat.name,
                    post_type=p["post_type"],
                    title=p.get("title", ""),
                    body=p.get("body", ""),
                )
                click.echo(f"  ✓ #{pid} [{plat.name}] {p['post_type']}: {(p.get('title') or '')[:50]}")

    count = len(get_pending_approval())
    click.echo(f"\n{count} post(s) queued. Run `adauto review` to approve before posting.")


# ── adauto check-engagement ───────────────────────────────────────────────────

@cli.command("check-engagement")
def check_engagement():
    """Poll platforms for upvotes/comments on recent posts and update learning data."""
    from .analytics import check_engagement_all
    click.echo("[engagement] polling platforms...")
    updated = check_engagement_all()
    click.echo(f"[engagement] updated {updated} posts")
    _show_scores()


def _show_scores():
    from .analytics import score_styles
    scores = score_styles()
    if not scores:
        return
    click.echo("\n=== Engagement Scores (learning) ===")
    click.echo(f"{'Platform':12} {'PostType':12} {'Posts':6} {'Avg↑':6} {'Avg💬':6} {'Score':7}")
    click.echo("─" * 55)
    for s in scores[:10]:
        click.echo(
            f"{s['platform']:12} {s['post_type']:12} {s['n_posts']:6d} "
            f"{s['avg_upvotes']:6.1f} {s['avg_comments']:6.1f} {s['total_score']:7.0f}"
        )


# ── adauto status ─────────────────────────────────────────────────────────────

@cli.command()
def status():
    """Show overall campaign statistics."""
    stats = get_stats()
    pending = get_pending_approval()
    approved = get_approved()

    click.echo("\n=== adauto status ===")

    if not stats and not pending and not approved:
        click.echo("No data yet. Run `adauto generate` to start.")
        return

    if pending:
        click.echo(f"\n⏳ {len(pending)} post(s) PENDING APPROVAL — run `adauto review`")
    if approved:
        click.echo(f"✅ {len(approved)} post(s) APPROVED, ready to publish — run `adauto post <campaign>`")

    if stats:
        click.echo()
        for platform, statuses in stats.items():
            total = sum(statuses.values())
            parts = "  ".join(f"{s}:{n}" for s, n in sorted(statuses.items()))
            click.echo(f"  {platform:12} [{parts}]  total={total}")

    _show_scores()


# ── adauto beacon ─────────────────────────────────────────────────────────────

@cli.command()
@click.option("--discover", is_flag=True, help="Discover other adauto instances on LAN")
@click.option("--timeout", default=3.0)
def beacon(discover, timeout):
    """Broadcast or discover adauto on the local network."""
    if discover:
        from .discover import discover as _discover
        click.echo(f"[beacon] scanning ({timeout}s)...")
        instances = _discover(timeout=timeout)
        if instances:
            for inst in instances:
                click.echo(f"  {inst['name']}: {inst['host']}:{inst['port']}")
        else:
            click.echo("  No adauto instances found on LAN")
    else:
        click.echo("To broadcast: start with `adauto serve` (mDNS is automatic)")


# ── adauto benchmark ──────────────────────────────────────────────────────────

@cli.command()
@click.argument("campaign_name")
@click.option("--platform", "-p", default="reddit")
@click.option("--count", "-n", default=3)
@click.option("--ds-url", default="http://localhost:8765")
def benchmark(campaign_name, platform, count, ds_url):
    """Benchmark deepstrain: generation speed and content quality."""
    camp = load_campaign(campaign_name)
    if not camp:
        click.echo(f"Campaign not found: {campaign_name}", err=True); sys.exit(1)

    from .generator import generate_batch
    from .analytics import best_post_type

    click.echo(f"\n[benchmark] {campaign_name}/{platform} × {count} posts via deepstrain")
    t0 = time.monotonic()
    posts = generate_batch(camp, platform, count=count, ds_url=ds_url or camp.deepstrain_url)
    elapsed = time.monotonic() - t0

    total_chars = sum(len(p.get("body","")) for p in posts)

    click.echo(f"\n{'='*50}")
    click.echo(f"Generated    : {len(posts)}/{count} posts")
    click.echo(f"Total time   : {elapsed:.1f}s")
    click.echo(f"Avg/post     : {elapsed/max(len(posts),1):.1f}s")
    click.echo(f"Avg chars    : {total_chars//max(len(posts),1)}")
    click.echo(f"Best style   : {best_post_type(campaign_name, platform)} (from history)")

    for i, p in enumerate(posts, 1):
        click.echo(f"\n─── Post {i} [{p.get('post_type')}] ───")
        click.echo(f"Title: {p.get('title','(none)')}")
        body = p.get("body","")
        click.echo(f"Body ({len(body)} chars): {body[:200]}{'...' if len(body)>200 else ''}")


def main():
    cli()


if __name__ == "__main__":
    main()
