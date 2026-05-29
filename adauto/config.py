"""Campaign configuration loader — TOML based."""
import tomllib
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

CONFIG_DIR = Path.home() / ".adauto"
CAMPAIGNS_DIR = CONFIG_DIR / "campaigns"


@dataclass
class Platform:
    name: str
    enabled: bool = True
    subreddits: list = field(default_factory=list)  # reddit only
    post_types: list = field(default_factory=lambda: ["showcase"])
    posts_per_day: float = 1.0
    cooldown_hours: int = 24  # min hours between posts to same subreddit


@dataclass
class Campaign:
    name: str
    product: str          # "deepstrain" | "code-atlas-py" | "adauto"
    tagline: str
    install_cmd: str      # e.g. "pip install deepstrain"
    repo_url: str
    site_url: str
    deepstrain_url: str = "http://localhost:8765"
    platforms: list = field(default_factory=list)  # list[Platform]
    enabled: bool = True
    demo_cmd: str = ""    # command used in VHS demo tapes
    # Rich product context — fed directly into generator prompts
    product_description: str = ""
    key_features: list = field(default_factory=list)
    differentiators: list = field(default_factory=list)
    target_audience: list = field(default_factory=list)
    pricing_note: str = ""

    @classmethod
    def from_toml(cls, path: Path) -> "Campaign":
        with open(path, "rb") as f:
            data = tomllib.load(f)
        platforms = []
        for pname, pcfg in data.get("platforms", {}).items():
            platforms.append(Platform(
                name=pname,
                enabled=pcfg.get("enabled", True),
                subreddits=pcfg.get("subreddits", []),
                post_types=pcfg.get("post_types", ["showcase"]),
                posts_per_day=pcfg.get("posts_per_day", 1.0),
                cooldown_hours=pcfg.get("cooldown_hours", 24),
            ))
        c = data["campaign"]
        return cls(
            name=c["name"],
            product=c["product"],
            tagline=c["tagline"],
            install_cmd=c["install_cmd"],
            repo_url=c["repo_url"],
            site_url=c["site_url"],
            deepstrain_url=c.get("deepstrain_url", "http://localhost:8765"),
            platforms=platforms,
            enabled=c.get("enabled", True),
            demo_cmd=c.get("demo_cmd", ""),
            product_description=c.get("product_description", "").strip(),
            key_features=c.get("key_features", []),
            differentiators=c.get("differentiators", []),
            target_audience=c.get("target_audience", []),
            pricing_note=c.get("pricing_note", ""),
        )

    def get_platform(self, name: str) -> Optional[Platform]:
        for p in self.platforms:
            if p.name == name:
                return p
        return None


def load_campaign(name: str) -> Optional[Campaign]:
    path = CAMPAIGNS_DIR / f"{name}.toml"
    if not path.exists():
        return None
    return Campaign.from_toml(path)


def list_campaigns() -> list[str]:
    CAMPAIGNS_DIR.mkdir(parents=True, exist_ok=True)
    return [p.stem for p in CAMPAIGNS_DIR.glob("*.toml")]
