"""adauto repo intake — point adauto at ANY repo, get a marketing campaign.

This is what turns adauto into a real product: a user (or an LLM acting for
them) says "this is my repo — bring me sales", and adauto builds a campaign.

Immortal by design (the ecosystem principle):
  • Deterministic core — parses README + manifest (pyproject/package.json/Cargo).
    Works with ZERO LLM, offline, always produces a usable campaign.
  • Optional deepstrain enrichment — if a brain is reachable, it sharpens the
    tagline, features, differentiators, audience and subreddits.
The brain is swappable; the campaign is always produced.
"""
from __future__ import annotations

import json
import re
import subprocess
import tomllib
from pathlib import Path

# language → seed subreddits (deterministic, used with no LLM)
_LANG_SUBS: dict[str, list[str]] = {
    "python":     ["Python", "programming", "SideProject", "learnpython"],
    "javascript": ["javascript", "webdev", "node", "SideProject"],
    "typescript": ["typescript", "webdev", "javascript", "SideProject"],
    "rust":       ["rust", "programming", "SideProject"],
    "go":         ["golang", "programming", "SideProject"],
    "default":    ["programming", "SideProject", "coding"],
}
_EXT_LANG = {".py": "python", ".js": "javascript", ".ts": "typescript",
             ".tsx": "typescript", ".rs": "rust", ".go": "go"}


def _read_readme(root: Path) -> tuple[str, str]:
    """Return (title, first_paragraph) from the README, deterministically."""
    for name in ("README.md", "README.rst", "README.txt", "readme.md", "Readme.md"):
        p = root / name
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^#\s+(.+)$", text, re.M)
        title = m.group(1).strip() if m else ""
        desc = ""
        for para in re.split(r"\n\s*\n", text):
            s = para.strip()
            if not s or s.startswith(("#", "![", "[", "<", "```", "|", "-", "*", ">")):
                continue
            desc = re.sub(r"\s+", " ", s)[:400]
            break
        return title, desc
    return "", ""


def _read_manifest(root: Path) -> dict:
    """Extract name/description/install_cmd/lang from a package manifest."""
    pp = root / "pyproject.toml"
    if pp.exists():
        try:
            proj = tomllib.loads(pp.read_text(encoding="utf-8")).get("project", {})
            if proj.get("name"):
                return {"name": proj["name"], "description": proj.get("description", ""),
                        "install_cmd": f"pip install {proj['name']}", "lang": "python"}
        except Exception:
            pass
    pj = root / "package.json"
    if pj.exists():
        try:
            data = json.loads(pj.read_text(encoding="utf-8"))
            if data.get("name"):
                return {"name": data["name"], "description": data.get("description", ""),
                        "install_cmd": f"npm install {data['name']}", "lang": "javascript"}
        except Exception:
            pass
    ct = root / "Cargo.toml"
    if ct.exists():
        try:
            pkg = tomllib.loads(ct.read_text(encoding="utf-8")).get("package", {})
            if pkg.get("name"):
                return {"name": pkg["name"], "description": pkg.get("description", ""),
                        "install_cmd": f"cargo add {pkg['name']}", "lang": "rust"}
        except Exception:
            pass
    return {}


def _git_remote(root: Path) -> str:
    try:
        r = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return r.stdout.strip().removesuffix(".git")
    except Exception:
        pass
    return ""


def _detect_lang(root: Path) -> str:
    counts: dict[str, int] = {}
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in _EXT_LANG:
            counts[p.suffix] = counts.get(p.suffix, 0) + 1
    if not counts:
        return "default"
    return _EXT_LANG.get(max(counts, key=counts.get), "default")


def intake(root_or_path: str) -> dict:
    """Deterministic repo → campaign metadata. Zero LLM, always works."""
    root = Path(root_or_path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")
    title, desc = _read_readme(root)
    man = _read_manifest(root)
    lang = man.get("lang") or _detect_lang(root)
    raw_name = man.get("name") or (title.split()[0] if title else root.name)
    name = re.sub(r"[^a-z0-9_-]", "", raw_name.lower()) or root.name.lower()
    description = desc or man.get("description", "")
    return {
        "name": name,
        "product": man.get("name") or name,
        "tagline": (man.get("description") or desc or title or name)[:120],
        "install_cmd": man.get("install_cmd") or f"# see {name} README",
        "repo_url": _git_remote(root),
        "site_url": "",
        "product_description": description,
        "lang": lang,
        "subreddits": _LANG_SUBS.get(lang, _LANG_SUBS["default"]),
        "_enriched": False,
    }


def enrich(meta: dict, ds_url: str = "http://localhost:8765", timeout: int = 90) -> dict:
    """Optional: sharpen the campaign with a brain (deepstrain /eval).

    Never raises and never blocks the pipeline — on any failure the
    deterministic meta is returned unchanged (immortality principle).
    """
    import urllib.request

    prompt = (
        "You are a developer-marketing strategist. Given this project, return ONLY a "
        "JSON object with keys: tagline (<=100 chars), key_features (3-5 short strings), "
        "differentiators (2-3 short strings), target_audience (2-4 short strings), "
        "subreddits (4-6 subreddit names without r/). No prose, JSON only.\n\n"
        f"name: {meta['name']}\nlanguage: {meta['lang']}\n"
        f"description: {meta.get('product_description','')[:600]}\n"
        f"current tagline: {meta.get('tagline','')}"
    )
    try:
        body = json.dumps({"prompt": prompt, "max_turns": 2}).encode()
        req = urllib.request.Request(
            ds_url.rstrip("/") + "/eval", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            answer = json.loads(r.read()).get("answer", "")
        m = re.search(r"\{.*\}", answer, re.DOTALL)
        if not m:
            return meta
        data = json.loads(m.group(0))
        out = dict(meta)
        if data.get("tagline"):
            out["tagline"] = str(data["tagline"])[:120]
        for k in ("key_features", "differentiators", "target_audience", "subreddits"):
            if isinstance(data.get(k), list) and data[k]:
                out[k] = [str(x) for x in data[k]]
        out["_enriched"] = True
        return out
    except Exception:
        return meta  # brain unreachable → deterministic campaign still ships


def _toml_list(items: list[str]) -> str:
    inner = ",\n    ".join(f'"{i}"' for i in items)
    return f"[\n    {inner},\n]" if items else "[]"


def to_toml(meta: dict) -> str:
    """Render campaign metadata as an adauto campaign TOML."""
    feats = meta.get("key_features", [])
    diffs = meta.get("differentiators", [])
    audience = meta.get("target_audience", [])
    lines = [
        "[campaign]",
        f'name         = "{meta["name"]}"',
        f'product      = "{meta["product"]}"',
        f'tagline      = "{meta["tagline"]}"',
        f'install_cmd  = "{meta["install_cmd"]}"',
        f'repo_url     = "{meta.get("repo_url","")}"',
        f'site_url     = "{meta.get("site_url","")}"',
        'deepstrain_url = "http://localhost:8765"',
        "enabled      = true",
        "",
        f'product_description = "{meta.get("product_description","").replace(chr(34), chr(39))[:500]}"',
    ]
    if feats:
        lines.append(f"key_features = {_toml_list(feats)}")
    if diffs:
        lines.append(f"differentiators = {_toml_list(diffs)}")
    if audience:
        lines.append(f"target_audience = {_toml_list(audience)}")
    lines += [
        "",
        "[platforms.reddit]",
        "enabled        = true",
        "posts_per_day  = 0.5",
        "cooldown_hours = 48",
        'post_types     = ["showcase", "tutorial", "question"]',
        f"subreddits     = {_toml_list(meta.get('subreddits', []))}",
        "",
        "[platforms.devto]",
        "enabled       = true",
        "posts_per_day = 0.25",
        'post_types    = ["tutorial", "showcase"]',
        "",
        "[platforms.twitter]",
        "enabled       = true",
        "posts_per_day = 1.0",
        'post_types    = ["showcase", "update"]',
        "",
    ]
    return "\n".join(lines)


def build_campaign(root_or_path: str, ds_url: str = "http://localhost:8765",
                   use_llm: bool = True) -> tuple[dict, str]:
    """Full pipeline: intake → (optional) enrich → TOML. Returns (meta, toml_text)."""
    meta = intake(root_or_path)
    if use_llm:
        meta = enrich(meta, ds_url=ds_url)
    return meta, to_toml(meta)
