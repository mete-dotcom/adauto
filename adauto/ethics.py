"""
adauto ethics & compliance filter — every post passes through this gate.

Two layers:
  1. Pattern layer  — regex + keyword matching (offline, instant, zero cost)
  2. Semantic check — optional deepstrain /eval pass for edge cases

Returns EthicsResult with:
  .allowed    bool
  .severity   "block" | "warn" | "ok"
  .violations list of human-readable explanations
  .categories set of matched rule categories

Default rules cover standard community guidelines.
User-configurable blocklist extends the defaults.

INVARIANTS:
  - Never modifies the post — only evaluates it
  - Never blocks on exception — degraded allow is safer than false-positive block
  - Violations are logged to adauto.log regardless of action taken
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import json

log = logging.getLogger("adauto.ethics")

# ── result dataclass ──────────────────────────────────────────────────────────

@dataclass
class EthicsResult:
    allowed:    bool          = True
    severity:   str           = "ok"         # "ok" | "warn" | "block"
    violations: list[str]     = field(default_factory=list)
    categories: set[str]      = field(default_factory=set)

    def __bool__(self) -> bool:
        return self.allowed


# ── rule definition ───────────────────────────────────────────────────────────

@dataclass
class Rule:
    category:    str
    severity:    str           # "block" or "warn"
    description: str
    patterns:    list[str]     # regex strings (case-insensitive)
    keywords:    list[str] = field(default_factory=list)   # literal keyword matches

    def matches(self, text: str) -> bool:
        t = text.lower()
        if any(kw.lower() in t for kw in self.keywords):
            return True
        for pat in self.patterns:
            try:
                if re.search(pat, t, re.IGNORECASE | re.DOTALL):
                    return True
            except re.error:
                pass
        return False


# ── built-in rule set ─────────────────────────────────────────────────────────

_BUILTIN_RULES: list[Rule] = [

    # ── Live animal & endangered species trade ────────────────────────────────
    Rule(
        category="live_animal_trade",
        severity="block",
        description="Live animal sales or trade (including exotic pets, livestock, wildlife)",
        patterns=[
            r"\b(sell|sale|buy|purchase|adopt|rehome|available)\b.{0,40}\b(puppy|puppies|kitten|kittens|dog|cat|bird|parrot|reptile|snake|turtle|fish|rabbit|hamster|guinea pig|livestock|cattle|horse|calf|lamb|chick|duckling)\b",
            r"\b(live|living|alive|fresh)\b.{0,20}\b(animal|pet|creature|specimen)\b.{0,30}\b(sale|sell|buy|available|ship|deliver)\b",
            r"\b(exotic|rare|endangered|protected)\b.{0,30}\b(animal|species|pet|bird|reptile)\b",
            r"\bCITES\b|\bwildlife trafficking\b|\billegal.*wildlife\b",
        ],
        keywords=["live bait for sale", "baby chicks for sale", "puppies for sale",
                  "kittens for sale", "exotic pets for sale", "live animals available"],
    ),

    # ── Illegal goods & substances ────────────────────────────────────────────
    Rule(
        category="illegal_goods",
        severity="block",
        description="Illegal goods, controlled substances, or black-market items",
        patterns=[
            r"\b(buy|sell|purchase|order|ship)\b.{0,30}\b(cocaine|heroin|meth|fentanyl|mdma|ecstasy|lsd|psilocybin|cannabis|weed|marijuana)\b",
            r"\b(unregistered|unlicensed|untraceable)\b.{0,20}\b(firearm|gun|weapon|pistol|rifle)\b",
            r"\bghost gun\b|\bpipe bomb\b|\b3d.?print.{0,10}gun\b",
            r"\b(fake|forged|counterfeit)\b.{0,20}\b(id|passport|document|currency|money)\b",
            r"\b(darkweb|dark web|onion.link|tor.market)\b",
        ],
        keywords=["buy drugs online", "illegal weapons", "counterfeit money",
                  "fake passport", "black market"],
    ),

    # ── Adult / explicit content ───────────────────────────────────────────────
    Rule(
        category="explicit_content",
        severity="block",
        description="Sexually explicit or adult content",
        patterns=[
            r"\b(pornography|explicit sex|adult content|nsfw.video|nude.photo)\b",
            r"\b(escort|prostitut|sex.worker|onlyfans.link)\b.{0,30}\b(buy|hire|contact|book)\b",
        ],
        keywords=["adult only", "18+ content", "explicit material"],
    ),

    # ── Child safety ──────────────────────────────────────────────────────────
    Rule(
        category="child_safety",
        severity="block",
        description="Content that could endanger or exploit minors",
        patterns=[
            r"\b(child|minor|underage|teen).{0,30}\b(explicit|nude|sexual|predator)\b",
            r"\bcsam\b|\bchild pornography\b|\bchild sexual abuse\b",
        ],
        keywords=[],
    ),

    # ── Weapons & violence ────────────────────────────────────────────────────
    Rule(
        category="weapons_violence",
        severity="block",
        description="Instructions for violence, weapon manufacture, or threats",
        patterns=[
            r"\b(how to|instructions|tutorial|guide).{0,30}\b(kill|murder|bomb|explosive|poison|weapon)\b",
            r"\b(threat|threaten).{0,20}\b(life|kill|hurt|harm|attack)\b",
            r"\b(bomb making|bioweapon|chemical weapon|mass casualty)\b",
        ],
        keywords=["how to make a bomb", "how to poison", "assassination guide"],
    ),

    # ── Hate speech & discrimination ──────────────────────────────────────────
    Rule(
        category="hate_speech",
        severity="block",
        description="Hate speech targeting ethnicity, religion, gender, sexuality, or disability",
        patterns=[
            r"\b(inferior|subhuman|vermin|parasite)\b.{0,30}\b(race|ethnic|religion|muslim|jewish|black|gay|lesbian|trans)\b",
            r"\b(exterminate|eliminate|cleanse)\b.{0,30}\b(race|ethnic|group|people|minority)\b",
        ],
        keywords=["racial slur", "ethnic cleansing", "neo-nazi", "white supremacy"],
    ),

    # ── Misleading claims & fake statistics ───────────────────────────────────
    Rule(
        category="misleading_claims",
        severity="block",
        description="Demonstrably false claims, fabricated statistics, or guaranteed outcomes",
        patterns=[
            r"\b(guarantee|guaranteed|100%.sure|never fail|always work)\b.{0,40}\b(rich|money|profit|earn|income|result)\b",
            r"\b(clinically proven|doctor(s)? recommend|fda approved)\b.{0,40}\b(cure|treat|heal|fix|eliminate)\b",
            r"\b(lose \d+ (lbs?|kg|pounds?|kilos?) in \d+ (day|week))\b",
            r"\b(make \$\d+|earn \$\d+).{0,20}\b(day|week|hour|overnight|fast)\b",
        ],
        keywords=["get rich quick", "100% guaranteed profit", "miracle cure",
                  "instant results guaranteed", "make money fast"],
    ),

    # ── Spam / engagement manipulation ────────────────────────────────────────
    Rule(
        category="spam",
        severity="block",
        description="Spam patterns, engagement manipulation, or vote buying",
        patterns=[
            r"\b(buy|purchase|boost)\b.{0,20}\b(upvote|downvote|follower|like|view|subscriber)\b",
            r"\b(upvote|like|share|retweet).{0,20}\b(for a chance|to win|giveaway)\b.{0,30}\bfollow\b",
            r"\bclick here to win\b|\bshare for free\b|\bforward this to \d+\b",
        ],
        keywords=["buy upvotes", "buy followers", "vote manipulation",
                  "click to win", "share to win free"],
    ),

    # ── Fake reviews & paid endorsements ─────────────────────────────────────
    Rule(
        category="fake_reviews",
        severity="block",
        description="Soliciting or offering fake/paid reviews",
        patterns=[
            r"\b(buy|paid|get|write|leave).{0,20}\b(fake|5.?star|positive)\b.{0,20}\breview\b",
            r"\b(review.{0,10}exchange|review.{0,10}swap|review.{0,10}incentiv)\b",
            r"\bpay.{0,15}\breview\b|\breview.{0,15}\bpay\b",
        ],
        keywords=["paid review", "fake review", "buy reviews", "review exchange"],
    ),

    # ── Pyramid / MLM schemes ─────────────────────────────────────────────────
    Rule(
        category="pyramid_scheme",
        severity="block",
        description="Pyramid schemes, MLM recruitment, or Ponzi-style structures",
        patterns=[
            r"\b(recruit|sign up|join).{0,30}\b(downline|upline|team|network)\b.{0,30}\b(commission|earn|income)\b",
            r"\b(passive income|residual income).{0,40}\b(recruit|refer|sign up)\b",
            r"\bpyramid scheme\b|\bponzi\b|\b(mlm|multi.?level.?marketing)\b.{0,30}\bjoin\b",
        ],
        keywords=["join my downline", "unlimited earning potential", "be your own boss MLM"],
    ),

    # ── Medical misinformation ────────────────────────────────────────────────
    Rule(
        category="medical_misinformation",
        severity="warn",
        description="Unverified medical claims or advice to replace professional care",
        patterns=[
            r"\b(cure|treat|heal|reverse).{0,30}\b(cancer|diabetes|hiv|aids|alzheimer|autism|covid)\b",
            r"\b(vaccine|vaccination).{0,20}\b(cause|causes|caused|link(ed)? to).{0,20}\b(autism|death|harm)\b",
            r"\bdon't (take|use|trust).{0,20}\b(medication|medicine|vaccine|doctor|hospital)\b",
        ],
        keywords=["cure cancer naturally", "vaccines cause autism",
                  "doctors don't want you to know"],
    ),

    # ── Financial advice / investment fraud ───────────────────────────────────
    Rule(
        category="financial_fraud",
        severity="warn",
        description="Unregistered investment advice or financial fraud patterns",
        patterns=[
            r"\b(guaranteed|risk.?free).{0,30}\b(investment|return|profit|yield)\b",
            r"\b(pump|dump).{0,10}\b(stock|coin|token|crypto)\b",
            r"\binsider.{0,10}tip\b|\bsure.?thing.{0,20}\binvest\b",
        ],
        keywords=["guaranteed investment returns", "risk-free profit",
                  "insider trading tip", "pump and dump"],
    ),

    # ── Excessive promotional spam ────────────────────────────────────────────
    Rule(
        category="over_promotional",
        severity="warn",
        description="Post is purely promotional with no value for the community",
        patterns=[
            r"(buy now|order today|limited time offer|act fast|don't miss out).{0,50}(buy now|order|click|visit|purchase)",
            r"\b(amazing|incredible|revolutionary|game.?changing|best ever)\b.{0,20}\b(product|software|tool|app|service)\b.{0,30}\b(amazing|incredible|revolutionary|game.?changing|best ever)\b",
        ],
        keywords=["buy now click here", "limited time offer buy today",
                  "don't miss out order now"],
    ),

    # ── Personal data harvesting ──────────────────────────────────────────────
    Rule(
        category="data_harvesting",
        severity="block",
        description="Requests for personal data under false pretenses",
        patterns=[
            r"\b(enter|submit|send).{0,30}\b(ssn|social security|passport number|credit card|bank account)\b",
            r"\bfree.{0,20}gift.{0,20}(enter|submit|provide).{0,30}\b(email|phone|address)\b.{0,30}\b(required|mandatory)\b",
        ],
        keywords=["enter your SSN", "provide credit card details",
                  "bank account required"],
    ),
]


# ── user-configurable extra blocklist ─────────────────────────────────────────
# Users can add extra blocked keywords/patterns to ~/.adauto/ethics_blocklist.json
# Format: [{"keywords": [...], "patterns": [...], "category": "...", "severity": "block"}]

_BLOCKLIST_PATH = Path.home() / ".adauto" / "ethics_blocklist.json"


def _load_user_rules() -> list[Rule]:
    if not _BLOCKLIST_PATH.exists():
        return []
    try:
        entries = json.loads(_BLOCKLIST_PATH.read_text(encoding="utf-8"))
        rules = []
        for e in entries:
            if isinstance(e, dict):
                rules.append(Rule(
                    category=e.get("category", "user_defined"),
                    severity=e.get("severity", "block"),
                    description=e.get("description", "User-defined rule"),
                    patterns=e.get("patterns", []),
                    keywords=e.get("keywords", []),
                ))
        return rules
    except Exception:
        return []


def _all_rules() -> list[Rule]:
    return _BUILTIN_RULES + _load_user_rules()


# ── main filter function ───────────────────────────────────────────────────────

def check(
    title: Optional[str] = None,
    body: Optional[str] = None,
    campaign_name: str = "",
    platform: str = "",
) -> EthicsResult:
    """
    Run ethics check on title + body.
    Never raises — degrades to allow on unexpected error.

    Returns EthicsResult:
        .allowed     False if any "block"-severity rule matched
        .severity    "block" | "warn" | "ok"
        .violations  human-readable list
        .categories  set of matched rule categories
    """
    combined = " ".join(filter(None, [title or "", body or ""])).strip()
    if not combined:
        return EthicsResult(allowed=True, severity="ok")

    result = EthicsResult(allowed=True, severity="ok")

    try:
        for rule in _all_rules():
            if rule.matches(combined):
                result.categories.add(rule.category)
                result.violations.append(
                    f"[{rule.severity.upper()}] {rule.category}: {rule.description}"
                )
                if rule.severity == "block":
                    result.allowed   = False
                    result.severity  = "block"
                elif rule.severity == "warn" and result.severity == "ok":
                    result.severity = "warn"

    except Exception as exc:
        # Never block on unexpected error — log and allow
        log.warning("ethics check error (allowing post): %s", exc)
        return EthicsResult(allowed=True, severity="ok")

    # Logging
    if result.violations:
        prefix = f"[{campaign_name}/{platform}]" if campaign_name else ""
        if not result.allowed:
            log.warning("%s ethics BLOCKED: %s", prefix, "; ".join(result.violations))
        else:
            log.info("%s ethics WARN: %s", prefix, "; ".join(result.violations))

    return result


def explain(result: EthicsResult) -> str:
    """Human-readable explanation of ethics check result."""
    if result.severity == "ok":
        return "OK — no violations"
    lines = [f"Ethics check ({result.severity.upper()}):"]
    for v in result.violations:
        lines.append(f"  {v}")
    if not result.allowed:
        lines.append("  -> Post BLOCKED. Revise content before re-generating.")
    else:
        lines.append("  -> Post WARNED. Review before publishing.")
    return "\n".join(lines)


def create_user_blocklist_example() -> None:
    """Write an example user blocklist to ~/.adauto/ethics_blocklist.json."""
    example = [
        {
            "category": "competitor_attack",
            "severity": "warn",
            "description": "Posts that directly attack named competitors",
            "keywords": [],
            "patterns": [r"\b(worse than|inferior to|scam unlike|fraud unlike)\b.{0,30}\b(our|my)\b"],
        },
        {
            "category": "custom_blocked_topic",
            "severity": "block",
            "description": "Example: gambling promotion",
            "keywords": ["online casino", "sports betting promo", "gambling bonus"],
            "patterns": [],
        },
    ]
    _BLOCKLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _BLOCKLIST_PATH.exists():
        _BLOCKLIST_PATH.write_text(json.dumps(example, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[ethics] example blocklist written to {_BLOCKLIST_PATH}")
