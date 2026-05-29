"""adauto CLI — multi-platform developer marketing automation."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Windows: reconfigure stdout/stderr to UTF-8 so Unicode symbols render correctly
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

import os
import click

from . import __version__
from .crash import run_cli, guard, log

# ── Credential loader (called before every command) ───────────────────────────

_CRED_FILE = Path.home() / ".adauto" / "credentials.env"


def _load_env_from_creds() -> None:
    """Load ~/.adauto/credentials.env into os.environ (only if not already set)."""
    if not _CRED_FILE.exists():
        return
    for line in _CRED_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip()
            if k and v and k not in os.environ:
                os.environ[k] = v
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
    # Auto-load platform credentials from ~/.adauto/credentials.env
    _load_env_from_creds()


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


# ── adauto init-from-repo (point adauto at YOUR repo) ────────────────────────

@cli.command("init-from-repo")
@click.argument("path", default=".")
@click.option("--name", default=None, help="Override campaign name")
@click.option("--ds-url", default="http://localhost:8765", help="deepstrain URL for enrichment")
@click.option("--no-llm", is_flag=True, default=False, help="Deterministic only — skip LLM enrichment")
@click.option("--force", is_flag=True, default=False, help="Overwrite existing campaign")
def init_from_repo(path, name, ds_url, no_llm, force):
    """Point adauto at YOUR repo -> auto-generate a marketing campaign.

    \b
    adauto init-from-repo .                 # current repo
    adauto init-from-repo ~/code/myproject  # any local repo
    adauto init-from-repo . --no-llm        # deterministic, offline

    Reads README + manifest (pyproject / package.json / Cargo) to build a
    campaign. If deepstrain is reachable it also sharpens tagline, features
    and target subreddits. Works either way — the brain is optional.
    """
    from .repo_intake import build_campaign
    from .config import CAMPAIGNS_DIR

    try:
        meta, toml_text = build_campaign(path, ds_url=ds_url, use_llm=not no_llm)
    except ValueError as e:
        click.echo(f"[error] {e}", err=True); sys.exit(1)

    cname = (name or meta["name"]).strip()
    CAMPAIGNS_DIR.mkdir(parents=True, exist_ok=True)
    dest = CAMPAIGNS_DIR / f"{cname}.toml"
    if dest.exists() and not force:
        click.echo(f"[exists] {dest} — use --force to overwrite", err=True); sys.exit(1)
    dest.write_text(toml_text, encoding="utf-8")

    brain = "deepstrain-enriched" if meta.get("_enriched") else "deterministic (no LLM)"
    click.echo(f"[ok] campaign '{cname}' created  ({brain})")
    click.echo(f"     product    : {meta['product']}")
    click.echo(f"     tagline    : {meta['tagline']}")
    click.echo(f"     subreddits : {', '.join(meta.get('subreddits', [])[:6])}")
    click.echo(f"     file       : {dest}")
    click.echo(f"\n  Next: adauto generate {cname}  ->  adauto review  ->  adauto post {cname}")


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

    Every post is shown in full — title, body, ethics status.
    Nothing is published without your explicit approval.
    """
    import json as _json
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.text import Text
        from rich.rule import Rule
        _console = Console()
        _USE_RICH = True
    except ImportError:
        _USE_RICH = False
        _console = None

    def _print(msg, style=""):
        if _USE_RICH:
            _console.print(msg, style=style)
        else:
            click.echo(msg)

    posts = get_pending_approval(campaign_name=campaign, platform=platform)
    if not posts:
        _print("\n  No posts pending approval.\n", style="dim")
        return

    _print(f"\n  {len(posts)} post(s) waiting for your review\n", style="bold")

    if approve_all:
        for p in posts:
            # Ethics Layer 2: re-check before bulk approve
            try:
                from .ethics import check as ec
                r = ec(p.get("title",""), p.get("body",""), p["campaign_name"], p["platform"])
                if not r.allowed:
                    _print(f"  [BLOCKED] #{p['id']} — ethics violation, skipping:", style="red")
                    for v in r.violations:
                        _print(f"    {v}", style="red")
                    skip_post(p["id"])
                    continue
            except Exception:
                pass
            approve_post(p["id"])
        _print(f"  Approved all {len(posts)} posts.", style="green")
        _print("  Run `adauto post` to publish.\n")
        return

    approved_count = 0
    skipped_count  = 0

    for i, p in enumerate(posts, 1):
        body  = p.get("body", "")
        title = p.get("title", "")

        # Parse ethics notes stored in DB
        eth_status = p.get("ethics_status", "ok")
        eth_notes: list = []
        try:
            raw = p.get("ethics_notes")
            if raw:
                eth_notes = _json.loads(raw)
        except Exception:
            pass

        if _USE_RICH:
            _console.print(Rule(
                f"[bold]Post #{p['id']}  [{i}/{len(posts)}][/bold]  "
                f"{p['campaign_name']} / {p['platform']} / {p['post_type']}"
            ))

            # Ethics status badge
            if eth_status == "warn":
                _console.print(Panel(
                    "\n".join(f"[yellow]⚠  {v}[/yellow]" for v in eth_notes),
                    title="[yellow]Ethics Warning[/yellow]",
                    border_style="yellow",
                ))
            elif eth_status == "block":
                _console.print(Panel(
                    "\n".join(f"[red]{v}[/red]" for v in eth_notes),
                    title="[red bold]Ethics BLOCK — approve anyway?[/red bold]",
                    border_style="red",
                ))

            # Title
            if title:
                _console.print(f"\n[bold cyan]TITLE:[/bold cyan] {title}")

            # Body — show FULL content, always
            _console.print(Panel(
                body if body else "[dim](no body)[/dim]",
                title=f"[bold]BODY  ({len(body)} chars)[/bold]",
                border_style="blue",
                padding=(1, 2),
            ))
        else:
            click.echo(f"\n[{i}/{len(posts)}] #{p['id']}  "
                       f"{p['campaign_name']}/{p['platform']}/{p['post_type']}")
            if eth_status == "warn":
                click.echo(f"  [ETHICS WARNING] {' | '.join(eth_notes)}")
            if title:
                click.echo(f"\nTITLE: {title}")
            click.echo(f"\nBODY ({len(body)} chars):\n{'─'*50}")
            click.echo(body)
            click.echo("─"*50)

        # Approval prompt
        while True:
            choice = click.prompt(
                "\n[a]pprove  [s]kip  [e]dit body  [q]uit",
                default="a",
            ).strip().lower()

            if choice in ("a", "approve", ""):
                # Ethics Layer 2: final check before approve
                try:
                    from .ethics import check as ec
                    r = ec(title, body, p["campaign_name"], p["platform"])
                    if not r.allowed:
                        _print(f"  Ethics BLOCK — cannot approve:", style="red bold")
                        for v in r.violations:
                            _print(f"    {v}", style="red")
                        _print("  Edit the content first or skip this post.", style="yellow")
                        continue
                except Exception:
                    pass
                approve_post(p["id"])
                _print("  Approved.", style="green bold")
                approved_count += 1
                break

            elif choice in ("s", "skip"):
                skip_post(p["id"])
                _print("  Skipped.", style="dim")
                skipped_count += 1
                break

            elif choice in ("e", "edit"):
                new_title = click.prompt("New title (enter to keep)", default=title)
                click.echo("Paste new body (end line with '---' alone to finish):")
                lines = []
                while True:
                    ln = input()
                    if ln == "---":
                        break
                    lines.append(ln)
                new_body = "\n".join(lines) if lines else body
                update_post_body(p["id"], new_title, new_body)
                approve_post(p["id"])
                _print("  Edited and approved.", style="green bold")
                approved_count += 1
                break

            elif choice in ("q", "quit"):
                _print(f"\n  Review paused — {approved_count} approved, {skipped_count} skipped.")
                return
            else:
                click.echo("  Use a / s / e / q")

        click.echo()

    if _USE_RICH:
        _console.print(Rule())
    _print(f"  Review complete: {approved_count} approved, {skipped_count} skipped")
    if approved_count > 0:
        _print("  Run `adauto post <campaign>` to publish approved posts.", style="bold")


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
        with guard(f"posting to {plat_name}"):
            if plat_name == "reddit":
                from .platforms.reddit import RedditPoster
                poster = RedditPoster()
                for p in posts:
                    subs = plat.subreddits or ["programming"]
                    with guard(f"reddit post #{p['id']}"):
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
            elif plat_name == "hackernews":
                from .platforms.hackernews import HackerNewsPoster
                poster = HackerNewsPoster()
                poster.run_campaign(camp, posts)
            else:
                click.echo(f"  [{plat_name}] no poster configured — skipping")

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


# ── adauto report ─────────────────────────────────────────────────────────────

@cli.command()
@click.argument("campaign_name", required=False, default=None)
def report(campaign_name):
    """Show ROI report: cost-per-score, best strategy, total spend.

    \b
    adauto report              # all campaigns
    adauto report deepstrain   # single campaign
    """
    from .server import _tool_report
    import json as _json
    results = _tool_report({"campaign": campaign_name} if campaign_name else {})
    if isinstance(results, list):
        if not results:
            click.echo("No data yet. Run `adauto generate` then `adauto post` first.")
            return
        for r in results:
            click.echo(f"\n[{r.get('campaign','?')}]")
            click.echo(f"  posts          : {r.get('total_posts', 0)}")
            click.echo(f"  engagement     : {r.get('total_engagement_score', 0):.0f}")
            click.echo(f"  cost USD       : ${r.get('estimated_total_cost_usd', 0):.4f}")
            cps = r.get('cost_per_score_point', 0)
            click.echo(f"  cost/score     : ${cps:.5f}" if cps else "  cost/score     : n/a")
            click.echo(f"  best strategy  : {r.get('best_strategy', 'insufficient_data')}")
    else:
        click.echo(_json.dumps(results, indent=2, ensure_ascii=False))


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
        click.echo(f"\n[pending] {len(pending)} post(s) PENDING APPROVAL — run `adauto review`")
    if approved:
        click.echo(f"[ready]   {len(approved)} post(s) APPROVED, ready to publish — run `adauto post <campaign>`")

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


# ── adauto demo ──────────────────────────────────────────────────────────────

@cli.group()
def demo():
    """Generate VHS .tape files and render terminal GIF demos for campaigns.

    \b
    adauto demo generate --campaign deepstrain  — write .tape file
    adauto demo render   --campaign deepstrain  — run vhs → .gif
    adauto demo list                            — show generated files
    """
    pass


@demo.command("generate")
@click.option("--campaign", "-c", required=True, help="Campaign name")
@click.option("--out-dir", default=None, help="Output directory (default: ~/.adauto/demos/)")
@click.option("--width",  default=900,  show_default=True)
@click.option("--height", default=520,  show_default=True)
@click.option("--theme",  default="Catppuccin Mocha", show_default=True)
def demo_generate(campaign, out_dir, width, height, theme):
    """Generate a VHS .tape file customised for the campaign."""
    from .config import load_campaign, CONFIG_DIR

    camp = load_campaign(campaign)
    if not camp:
        click.echo(f"Campaign not found: {campaign}", err=True); sys.exit(1)

    demos_dir = Path(out_dir) if out_dir else CONFIG_DIR / "demos"
    demos_dir.mkdir(parents=True, exist_ok=True)

    tape_path = demos_dir / f"{campaign}.tape"

    # Build tape content from campaign config
    install_cmd  = getattr(camp, "install_cmd",  f"pip install {camp.product}")
    product      = getattr(camp, "product",      campaign)
    tagline      = getattr(camp, "tagline",       "")
    example_cmd  = getattr(camp, "demo_cmd",     f'{product.split()[0]} eval "fix all test failures"')
    site_url     = getattr(camp, "site_url",     "")

    tape_content = f"""Output {campaign}.gif
Set Shell "bash"
Set FontSize 14
Set Width {width}
Set Height {height}
Set Theme "{theme}"
Set Padding 20
Set TypingSpeed 50ms
Set WaitTimeout 30s

# generated by adauto demo generate --campaign {campaign}
# product: {product}
# tagline: {tagline}

Sleep 500ms

Type "pip install {product}"
Enter
Sleep 4s

Type "{product} configure"
Enter
Sleep 2s

Type "{example_cmd}"
Enter
Sleep 8s

# tagline: {tagline}
# {site_url if site_url else ""}
Sleep 3s
"""

    tape_path.write_text(tape_content, encoding="utf-8")
    click.echo(f"[demo] tape written: {tape_path}")
    click.echo(f"[demo] render with:  adauto demo render --campaign {campaign}")
    click.echo(f"[demo] or directly:  vhs {tape_path}")


@demo.command("render")
@click.option("--campaign", "-c", required=True, help="Campaign name")
@click.option("--out-dir", default=None, help="Directory containing the .tape file")
@click.option("--gif-dir", default=None, help="Where to write the .gif (default: same as tape)")
def demo_render(campaign, out_dir, gif_dir):
    """Render a .tape file to animated GIF using Charmbracelet VHS.

    Requires `vhs` to be installed: https://github.com/charmbracelet/vhs
    On macOS/Linux: brew install charmbracelet/tap/vhs
    On Windows:     scoop install vhs  (or download binary)
    """
    import subprocess
    import shutil
    from .config import CONFIG_DIR

    demos_dir = Path(out_dir) if out_dir else CONFIG_DIR / "demos"
    tape_path = demos_dir / f"{campaign}.tape"

    if not tape_path.exists():
        click.echo(f"[demo] tape not found: {tape_path}", err=True)
        click.echo(f"[demo] run first:  adauto demo generate --campaign {campaign}", err=True)
        sys.exit(1)

    vhs_bin = shutil.which("vhs")
    if not vhs_bin:
        click.echo("[demo] vhs not found. Install: https://github.com/charmbracelet/vhs", err=True)
        click.echo(f"[demo] tape is ready at: {tape_path} — run manually: vhs {tape_path}", err=True)
        sys.exit(1)

    out_gif = (Path(gif_dir) if gif_dir else demos_dir) / f"{campaign}.gif"

    click.echo(f"[demo] rendering {tape_path} → {out_gif}")
    try:
        result = subprocess.run(
            [vhs_bin, str(tape_path), "-o", str(out_gif)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            click.echo(f"[demo] vhs error:\n{result.stderr}", err=True)
            sys.exit(1)
        size_kb = out_gif.stat().st_size // 1024
        click.echo(f"[demo] ✓ rendered: {out_gif}  ({size_kb} KB)")
        click.echo(f"[demo] copy to public/demos/ to serve from the site:")
        click.echo(f"       cp {out_gif} <site>/public/demos/{campaign}.gif")
    except subprocess.TimeoutExpired:
        click.echo("[demo] vhs timed out (>120s). Try reducing complexity in the tape.", err=True)
        sys.exit(1)


@demo.command("list")
@click.option("--out-dir", default=None)
def demo_list(out_dir):
    """List generated tape and GIF files."""
    from .config import CONFIG_DIR
    demos_dir = Path(out_dir) if out_dir else CONFIG_DIR / "demos"
    if not demos_dir.exists():
        click.echo("No demo files yet. Run `adauto demo generate --campaign <name>`")
        return
    files = sorted(demos_dir.iterdir())
    if not files:
        click.echo(f"No files in {demos_dir}")
        return
    for f in files:
        size = f.stat().st_size
        click.echo(f"  {f.name:40s} {size:>8,} bytes")


# ── adauto configure ─────────────────────────────────────────────────────────

def _load_creds() -> dict:
    if not _CRED_FILE.exists():
        return {}
    creds = {}
    for line in _CRED_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            creds[k.strip()] = v.strip()
    return creds


def _save_creds(creds: dict) -> None:
    _CRED_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# adauto platform credentials — auto-generated, do not commit\n"]
    for k, v in sorted(creds.items()):
        lines.append(f"{k}={v}\n")
    _CRED_FILE.write_text("".join(lines), encoding="utf-8")
    try:
        import stat
        _CRED_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass


@cli.command()
@click.option("--platform", "-p",
              type=click.Choice(["reddit", "twitter", "devto", "all"], case_sensitive=False),
              default="all", show_default=True,
              help="Which platform to configure")
@click.option("--show", is_flag=True, help="Show current credential status (masked)")
def configure(platform, show):
    """Set platform API credentials (Reddit, Twitter, dev.to).

    \b
    Credentials are stored in ~/.adauto/credentials.env (user-only permissions).
    They are loaded automatically when adauto starts — no manual export needed.

    \b
    adauto configure              # configure all platforms
    adauto configure -p reddit    # only Reddit
    adauto configure --show       # show what's set (masked)
    """
    import os
    _load_env_from_creds()
    creds = _load_creds()

    if show:
        keys_by_platform = {
            "reddit": ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET",
                       "REDDIT_USERNAME", "REDDIT_PASSWORD", "REDDIT_USER_AGENT"],
            "twitter": ["TWITTER_API_KEY", "TWITTER_API_SECRET",
                        "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET",
                        "TWITTER_BEARER_TOKEN"],
            "devto": ["DEVTO_API_KEY"],
        }
        click.echo("\n=== adauto credentials ===")
        for pname, keys in keys_by_platform.items():
            click.echo(f"\n[{pname}]")
            for k in keys:
                val = creds.get(k) or os.environ.get(k, "")
                if val:
                    masked = val[:4] + "****" if len(val) > 4 else "****"
                    click.echo(f"  {k:<32} = {masked}  [SET]")
                else:
                    click.echo(f"  {k:<32} = (not set)")
        click.echo()
        return

    platforms_to_configure = (
        ["reddit", "twitter", "devto"] if platform == "all" else [platform]
    )

    updated = {}

    for pname in platforms_to_configure:
        click.echo(f"\n--- {pname.upper()} ---")

        if pname == "reddit":
            click.echo("Get credentials at: https://www.reddit.com/prefs/apps")
            click.echo("Create a 'script' type app. Use your Reddit username/password.\n")
            updated["REDDIT_CLIENT_ID"]     = click.prompt("REDDIT_CLIENT_ID    ", default=creds.get("REDDIT_CLIENT_ID", ""))
            updated["REDDIT_CLIENT_SECRET"] = click.prompt("REDDIT_CLIENT_SECRET", default=creds.get("REDDIT_CLIENT_SECRET", ""), hide_input=True)
            updated["REDDIT_USERNAME"]      = click.prompt("REDDIT_USERNAME     ", default=creds.get("REDDIT_USERNAME", ""))
            updated["REDDIT_PASSWORD"]      = click.prompt("REDDIT_PASSWORD     ", default=creds.get("REDDIT_PASSWORD", ""), hide_input=True)
            updated["REDDIT_USER_AGENT"]    = click.prompt("REDDIT_USER_AGENT   ", default=creds.get("REDDIT_USER_AGENT", f"adauto/{__version__} by your-reddit-username"))

        elif pname == "twitter":
            click.echo("Get credentials at: https://developer.twitter.com/en/portal/apps")
            click.echo("Needs 'Read and Write' permissions.\n")
            updated["TWITTER_API_KEY"]        = click.prompt("TWITTER_API_KEY       ", default=creds.get("TWITTER_API_KEY", ""))
            updated["TWITTER_API_SECRET"]     = click.prompt("TWITTER_API_SECRET    ", default=creds.get("TWITTER_API_SECRET", ""), hide_input=True)
            updated["TWITTER_ACCESS_TOKEN"]   = click.prompt("TWITTER_ACCESS_TOKEN  ", default=creds.get("TWITTER_ACCESS_TOKEN", ""))
            updated["TWITTER_ACCESS_SECRET"]  = click.prompt("TWITTER_ACCESS_SECRET ", default=creds.get("TWITTER_ACCESS_SECRET", ""), hide_input=True)
            updated["TWITTER_BEARER_TOKEN"]   = click.prompt("TWITTER_BEARER_TOKEN  ", default=creds.get("TWITTER_BEARER_TOKEN", ""), hide_input=True)

        elif pname == "devto":
            click.echo("Get API key at: https://dev.to/settings/extensions → DEV Community API Keys\n")
            updated["DEVTO_API_KEY"] = click.prompt("DEVTO_API_KEY", default=creds.get("DEVTO_API_KEY", ""), hide_input=True)

    # Merge with existing
    creds.update({k: v for k, v in updated.items() if v.strip()})
    _save_creds(creds)
    click.echo(f"\n[ok] Credentials saved to {_CRED_FILE}")
    click.echo("     Run `adauto configure --show` to verify.\n")


# ── adauto license ────────────────────────────────────────────────────────────

@cli.group()
def license():
    """Manage adauto license (Paddle)."""
    pass


@license.command("activate")
@click.argument("key")
def license_activate(key):
    """Activate a license key. Get yours at adauto.dev"""
    from .license import activate
    result = activate(key)
    if result["ok"]:
        click.echo(f"✓ {result['message']}")
    else:
        click.echo(f"✗ {result['message']}", err=True)
        sys.exit(1)


@license.command("recover")
@click.option("--key",     required=True, help='Recovery token (starts with "RK1-AA-")')
@click.option("--email",   required=True, help="The email address on your receipt")
@click.option("--sale-id", required=True, help="Paddle order/subscription ID from your receipt")
def license_recover(key, email, sale_id):
    """Manual activation using a one-time recovery key from support.

    \b
    Use this when adauto license activate fails even though you paid.
    Contact support to get a recovery key, then run:

      adauto license recover \\
        --key "RK1-AA-..." \\
        --email you@example.com \\
        --sale-id sub_xxxxx
    """
    from .license import activate_recovery
    result = activate_recovery(token=key, email=email, sale_id=sale_id)
    if result["ok"]:
        click.echo(f"[ok] {result['message']}")
    else:
        click.echo(f"[error] {result['message']}", err=True)
        sys.exit(1)


@license.command("status")
def license_status():
    """Show current license status."""
    from .license import status as lic_status
    s = lic_status()
    if s["licensed"]:
        click.echo(f"✓ Licensed  tier={s['tier']}  key={s['key']}")
    else:
        click.echo(f"  Free tier  ({s['campaigns_allowed']} campaign, {s['posts_per_day_allowed']} posts/day)")
        click.echo(f"  {s['message']}")


def main():
    """Entry point — wraps cli() with a top-level crash guard."""
    run_cli(cli)


if __name__ == "__main__":
    main()
