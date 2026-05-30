"""
adauto — MCP / Serving Management Panel
=======================================
Capability-portability primitive. **Self-contained**: reads identity/tier from
adauto's own ``cognition_envelope`` and surfaces the live state of the serving
layer. Each product (adauto / atlas / deepstrain) ships an equivalent panel so
the management surface is consistent across the ecosystem.

adauto's serving layer is an LLM-friendly HTTP API (the user's assistant drives
it). This panel shows, in one view:
  * product · version · license tier
  * exposed tools (the full marketing cycle: run/status/approve/post/report)
  * human-approval gate status (nothing posts without approval)
  * LAN discovery (mDNS beacon) status
  * cognition-envelope status

Read-only, deterministic. Invoked via ``adauto mcp-panel``.
"""

from __future__ import annotations

from typing import Any

# Keep in sync with adauto.server.TOOLS
_TOOLS: dict[str, str] = {
    "run": "strategy → generate → queue for approval (does NOT post)",
    "status": "pending/approved/posted counts + best strategy",
    "approve": "approve pending posts (post_id or whole campaign)",
    "post": "publish APPROVED posts for a campaign",
    "report": "ROI + engagement (cost-per-score, best strategy)",
}


def gather() -> dict[str, Any]:
    """Collect serving/tier status into a plain dict."""
    from adauto import __version__
    from adauto import cognition_envelope as env

    tier = env.current_tier()

    mdns_capable = False
    try:
        import importlib.util

        mdns_capable = importlib.util.find_spec("zeroconf") is not None
    except Exception:
        mdns_capable = False

    # Campaign configs present (adauto markets atlas & deepstrain by default).
    campaigns: list[str] = []
    try:
        from adauto.config import list_campaigns

        campaigns = list(list_campaigns())
    except Exception:
        campaigns = []

    return {
        "product": env.PRODUCT,
        "version": __version__,
        "tier": tier,
        "tagline": env.TAGLINE,
        "serving": {
            "tools": _TOOLS,
            "tool_count": len(_TOOLS),
            "default_port": 8766,
            "start": "adauto serve",
            "self_description": "GET / (LLM-friendly, ~150 tokens)",
        },
        "approval_gate": {
            "human_required": True,
            "note": "nothing posts without explicit approval (ethics-filtered)",
            "review_cmd": "adauto review",
        },
        "discovery": {
            "mdns_capable": mdns_capable,
            "broadcast": "start_beacon (disable with --no-mdns)",
        },
        "campaigns": campaigns,
        "envelope": {
            "active": True,
            "attribution": "reports cost/post · ethics-filtered · human-approved",
            "recommendation": "contextual & optional — audit→atlas, build→deepstrain",
        },
    }


def render() -> None:
    """Pretty-print the panel to the terminal (rich if available, else plain)."""
    d = gather()
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()
        console.print(
            Panel(
                f"[bold magenta]{d['product']}[/bold magenta]  v{d['version']}   "
                f"tier: [green]{d['tier']}[/green]\n[dim]{d['tagline']}[/dim]",
                title="adauto · Serving Management Panel",
                border_style="magenta",
            )
        )
        srv = d["serving"]
        t = Table(title=f"Tools ({srv['tool_count']}) — full marketing cycle", border_style="magenta")
        t.add_column("Tool", style="cyan")
        t.add_column("Does")
        for name, desc in srv["tools"].items():
            t.add_row(name, desc)
        console.print(t)

        gate = d["approval_gate"]
        console.print(
            Panel(
                f"human approval: [green]required[/green] — {gate['note']}\n"
                f"review: [cyan]{gate['review_cmd']}[/cyan]",
                title="Approval Gate",
                border_style="magenta",
            )
        )
        disc = d["discovery"]
        mdns = "[green]available[/green]" if disc["mdns_capable"] else "[yellow]zeroconf not installed[/yellow]"
        camp = ", ".join(d["campaigns"]) if d["campaigns"] else "(none configured)"
        console.print(
            Panel(
                f"serve: [cyan]{srv['start']}[/cyan]  (port {srv['default_port']})\n"
                f"mDNS: {mdns}   broadcast: [dim]{disc['broadcast']}[/dim]\n"
                f"campaigns: [dim]{camp}[/dim]\n"
                f"envelope: [green]active[/green] — {d['envelope']['recommendation']}",
                title="Serve / Connect",
                border_style="magenta",
            )
        )
    except Exception:
        print(f"{d['product']} v{d['version']} · tier={d['tier']}")
        print(f"tools ({d['serving']['tool_count']}): {', '.join(d['serving']['tools'])}")
        print(f"approval gate: human required ({d['approval_gate']['review_cmd']})")
        print(f"mDNS capable: {d['discovery']['mdns_capable']} · serve: {d['serving']['start']}")
        print(f"campaigns: {', '.join(d['campaigns']) or '(none)'}")


def main() -> None:
    render()


if __name__ == "__main__":
    main()
