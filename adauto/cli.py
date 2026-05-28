"""adauto CLI — multi-platform ad automation."""
import os
import sys
import json
import time
from pathlib import Path

import click

from . import __version__
from .db import init_db, get_stats, get_queued
from .config import load_campaign, list_campaigns, CAMPAIGNS_DIR, Campaign
from .generator import generate_batch
from .scheduler import due_platforms, record_run


@click.group()
@click.version_option(__version__)
def cli():
    """adauto — automated developer marketing for multiple platforms."""
    init_db()


# ---------------------------------------------------------------------------
# adauto init
# ---------------------------------------------------------------------------
@cli.command()
def init():
    """Initialize adauto database and config directories."""
    from .config import CONFIG_DIR
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CAMPAIGNS_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    click.echo(f"[adauto] initialized at {CONFIG_DIR}")
    click.echo(f"[adauto] drop campaign TOML files in: {CAMPAIGNS_DIR}")


# ---------------------------------------------------------------------------
# adauto campaigns
# ---------------------------------------------------------------------------
@cli.command()
def campaigns():
    """List available campaigns."""
    names = list_campaigns()
    if not names:
        click.echo("No campaigns found. Add .toml files to ~/.adauto/campaigns/")
        return
    for n in names:
        camp = load_campaign(n)
        status = "enabled" if camp and camp.enabled else "disabled"
        platforms = ", ".join(p.name for p in camp.platforms) if camp else "?"
        click.echo(f"  {n:20s}  [{status}]  platforms: {platforms}")


# ---------------------------------------------------------------------------
# adauto generate
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("campaign_name")
@click.option("--platform", "-p", default=None,
              help="Platform to generate for (reddit/devto/twitter). Default: all.")
@click.option("--count", "-n", default=3, show_default=True,
              help="Number of posts to generate per platform.")
@click.option("--post-type", default=None,
              help="Override post type (showcase/tutorial/question/update).")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Save generated posts to JSON file.")
def generate(campaign_name, platform, count, post_type, output):
    """Generate posts for a campaign using deepstrain."""
    camp = load_campaign(campaign_name)
    if not camp:
        click.echo(f"Campaign not found: {campaign_name}", err=True)
        sys.exit(1)

    platforms = [p for p in camp.platforms if p.enabled]
    if platform:
        platforms = [p for p in platforms if p.name == platform]

    if not platforms:
        click.echo("No enabled platforms found.", err=True)
        sys.exit(1)

    all_posts = []
    for plat in platforms:
        types = [post_type] if post_type else plat.post_types
        click.echo(f"\n[generate] {campaign_name}/{plat.name} — {count} posts...")
        posts = generate_batch(camp, plat.name, count=count,
                               post_types=types,
                               ds_url=camp.deepstrain_url)
        for p in posts:
            click.echo(f"  [{p['post_type']}] {p.get('title', '')[:60] or p.get('body','')[:60]}")
        all_posts.extend(posts)

    if output:
        Path(output).write_text(json.dumps(all_posts, indent=2, ensure_ascii=False))
        click.echo(f"\n[generate] saved {len(all_posts)} posts to {output}")
    else:
        click.echo(f"\n[generate] {len(all_posts)} posts generated")
        click.echo("Use --output to save, or `adauto post` to publish")


# ---------------------------------------------------------------------------
# adauto post
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("campaign_name")
@click.option("--platform", "-p", default=None)
@click.option("--from-file", "-f", type=click.Path(exists=True), default=None,
              help="Use pre-generated posts JSON instead of generating new ones.")
@click.option("--dry-run", is_flag=True, default=False,
              help="Print what would be posted without actually posting.")
def post(campaign_name, platform, from_file, dry_run):
    """Generate and post content for a campaign."""
    camp = load_campaign(campaign_name)
    if not camp:
        click.echo(f"Campaign not found: {campaign_name}", err=True)
        sys.exit(1)

    platforms = [p for p in camp.platforms if p.enabled]
    if platform:
        platforms = [p for p in platforms if p.name == platform]

    for plat in platforms:
        if from_file:
            import json as _json
            all_posts = _json.loads(Path(from_file).read_text())
            plat_posts = [p for p in all_posts if p.get("platform") == plat.name]
        else:
            click.echo(f"[post] generating posts for {plat.name}...")
            plat_posts = generate_batch(camp, plat.name, count=len(plat.subreddits or [1]),
                                        ds_url=camp.deepstrain_url)

        if not plat_posts:
            click.echo(f"[post] no posts for {plat.name}")
            continue

        _run_platform(camp, plat, plat_posts, dry_run)
        if not dry_run:
            record_run(camp.name, plat.name)


def _run_platform(camp, plat, posts, dry_run):
    name = plat.name
    try:
        if name == "reddit":
            from .platforms.reddit import RedditPoster
            poster = RedditPoster()
            poster.run_campaign(camp, posts, dry_run=dry_run)
        elif name == "devto":
            from .platforms.devto import DevtoPoster
            poster = DevtoPoster()
            poster.run_campaign(camp, posts, dry_run=dry_run)
        elif name == "twitter":
            from .platforms.twitter import TwitterPoster
            poster = TwitterPoster()
            poster.run_campaign(camp, posts, dry_run=dry_run)
        else:
            click.echo(f"[post] unknown platform: {name}")
    except RuntimeError as e:
        click.echo(f"[{name}] skipped — {e}")


# ---------------------------------------------------------------------------
# adauto run  (scheduler loop — runs due campaigns)
# ---------------------------------------------------------------------------
@cli.command()
@click.option("--once", is_flag=True, default=False,
              help="Run due campaigns once and exit (default: loop every hour).")
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--campaign", "-c", default=None,
              help="Limit to one campaign.")
def run(once, dry_run, campaign):
    """Run the scheduler — posts to due platforms automatically."""
    while True:
        names = [campaign] if campaign else list_campaigns()
        for name in names:
            camp = load_campaign(name)
            if not camp or not camp.enabled:
                continue
            due = due_platforms(camp)
            if not due:
                click.echo(f"[run] {name} — nothing due")
                continue
            for plat in due:
                click.echo(f"[run] {name}/{plat.name} is due — generating...")
                posts = generate_batch(camp, plat.name,
                                       count=max(1, len(plat.subreddits or [1])),
                                       ds_url=camp.deepstrain_url)
                _run_platform(camp, plat, posts, dry_run)
                if not dry_run:
                    record_run(camp.name, plat.name)

        if once:
            break
        click.echo("[run] sleeping 60 min...")
        time.sleep(3600)


# ---------------------------------------------------------------------------
# adauto status
# ---------------------------------------------------------------------------
@cli.command()
def status():
    """Show posting statistics."""
    stats = get_stats()
    if not stats:
        click.echo("No posts yet.")
        return
    click.echo("\n=== adauto status ===")
    for platform, statuses in stats.items():
        total = sum(statuses.values())
        click.echo(f"\n{platform}:")
        for s, n in sorted(statuses.items()):
            bar = "█" * min(n, 20)
            click.echo(f"  {s:10s} {n:4d}  {bar}")
        click.echo(f"  {'TOTAL':10s} {total:4d}")

    queued = get_queued()
    if queued:
        click.echo(f"\n{len(queued)} post(s) in queue:")
        for q in queued[:5]:
            click.echo(f"  #{q['id']} [{q['platform']}] {q['post_type']} — {(q['title'] or '')[:50]}")


# ---------------------------------------------------------------------------
# adauto benchmark
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("campaign_name")
@click.option("--platform", "-p", default="reddit")
@click.option("--count", "-n", default=3)
def benchmark(campaign_name, platform, count):
    """Benchmark deepstrain: measure token savings and generation speed."""
    import time as _t

    camp = load_campaign(campaign_name)
    if not camp:
        click.echo(f"Campaign not found: {campaign_name}", err=True)
        sys.exit(1)

    click.echo(f"\n[benchmark] {campaign_name} / {platform} — {count} posts")
    click.echo(f"[benchmark] deepstrain URL: {camp.deepstrain_url}")

    t0 = _t.monotonic()
    posts = generate_batch(camp, platform, count=count, ds_url=camp.deepstrain_url)
    elapsed = _t.monotonic() - t0

    total_chars = sum(len(p.get("body", "")) for p in posts)
    avg_chars = total_chars / len(posts) if posts else 0

    click.echo(f"\n=== Benchmark Results ===")
    click.echo(f"Posts generated : {len(posts)}/{count}")
    click.echo(f"Total time      : {elapsed:.1f}s")
    click.echo(f"Avg time/post   : {elapsed/max(len(posts),1):.1f}s")
    click.echo(f"Total chars     : {total_chars}")
    click.echo(f"Avg chars/post  : {avg_chars:.0f}")

    for i, p in enumerate(posts, 1):
        click.echo(f"\n--- Post {i} [{p.get('post_type')}] ---")
        click.echo(f"Title: {p.get('title', '(none)')}")
        click.echo(f"Body ({len(p.get('body',''))} chars):\n{p.get('body','')[:300]}{'...' if len(p.get('body','')) > 300 else ''}")


def main():
    cli()


if __name__ == "__main__":
    main()
