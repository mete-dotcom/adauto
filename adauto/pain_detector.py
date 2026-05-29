"""
adauto pain detector — map real developer pain to product solutions.

Zero LLM cost. Deterministic regex patterns extracted from real-world
developer complaints. When a signal matches a pain pattern, we know
exactly which product helps and how to frame the response genuinely.

Philosophy:
  We don't promote. We help. The product is mentioned as a tool, not a brand.
  Every response is genuinely useful even if the reader ignores the product mention.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class PainMatch:
    pattern_id: str
    product: str            # atlas | deepstrain | adauto | bundle
    pain_summary: str       # what the person is experiencing
    solution_hook: str      # one-sentence genuine help offer
    response_template: str  # full response template (filled at render time)
    confidence: float       # 0–1
    matched_phrases: list[str] = field(default_factory=list)


# ── pain pattern library ──────────────────────────────────────────────────────
# Each entry: (pattern_id, product, regex_list, pain_summary, solution_hook, template)

_PATTERNS: list[tuple] = [

    # ── atlas: codebase too large / lost in code ──────────────────────────────
    (
        "large_codebase_lost",
        "atlas",
        [
            r"\b(codebase|repo|project)\b.{0,40}\b(too large|too big|grown|massive|huge|50k|80k|100k|thousands of (lines|files))\b",
            r"\b\d{2,3}k.{0,10}(line|loc|function|file)\b",
            r"\b(monolith|monolithic).{0,40}\b(lost|navigate|understand|debug|find)\b",
            r"\b(lost|drowning|overwhelmed)\b.{0,30}\b(code|codebase|files|functions)\b",
            r"\b(can'?t|cannot|hard to)\b.{0,30}\b(navigate|understand|follow|find)\b.{0,30}\b(code|codebase|project)\b",
            r"\binherited.{0,30}\b(codebase|project|repo)\b",
            r"\b(legacy|old|ancient|spaghetti)\b.{0,20}\b(code|codebase|system)\b.{0,30}\b(understand|navigate|maintain|debug)\b",
        ],
        "Codebase too large to navigate mentally",
        "atlas maps the full call graph + risk in ~0.2s, no LLM needed",
        """\
Sounds like a navigation problem more than a code problem. When a codebase \
hits a certain size, mental models break down faster than you can rebuild them.

One thing that helped me: `atlas scan .` (pip install atlas-intel) — it builds \
the full call graph and surfaces which functions are highest risk, what depends \
on what, and where the complexity is actually hiding. Runs locally, no cloud, \
takes a few seconds. The HTML report is self-contained so you can share it.

Might at least show you *where* the bug is likely hiding before you start reading.\
""",
    ),

    # ── atlas: AI-generated code nobody understands ───────────────────────────
    (
        "ai_generated_mystery",
        "atlas",
        [
            r"\b(ai|llm|gpt|claude|copilot|cursor|vibe.?cod)\b.{0,40}\b(wrote|generated|built|created)\b.{0,30}\b(code|this|it)\b",
            r"\b(vibe.?cod|ai.?generat)\b",
            r"\b(generated|ai.written|copilot.wrote)\b.{0,30}\b(don'?t understand|can'?t understand|no idea|mystery|mess)\b",
            r"\b(ai wrote|gpt wrote|claude wrote|copilot wrote|cursor (wrote|built|made))\b",
            r"\b(used|using)\b.{0,20}\b(cursor|copilot|claude|gpt|ai)\b.{0,40}\b(broke|broken|error|fail|crash|bug|now it)\b",
            r"\b(ai wrote|gpt wrote|claude wrote)\b.{0,50}\b(broke|breaking|error|fail|crash|bug)\b",
        ],
        "AI wrote the code, now it's broken and unreadable",
        "atlas shows exactly what the AI built — call graph, risk, what calls what",
        """\
Classic AI-generated code problem — it works until it doesn't, and then there's \
no mental model to debug from.

`atlas scan .` (pip install atlas-intel) is good here because it doesn't try to \
*understand* the code semantically — it just maps what's actually there: call graph, \
complexity per function, which parts are structurally risky. Offline, deterministic, \
no LLM. The interactive graph makes it easier to see the structure the AI created \
even when the code itself gives no hints.

What error are you hitting? The call graph might show you the blast radius quickly.\
""",
    ),

    # ── atlas + deepstrain: can't find the bug / stacktrace useless ──────────
    (
        "cant_find_bug",
        "bundle",
        [
            r"\b(can'?t|cannot|hard to)\b.{0,30}\b(find|locate|trace|track)\b.{0,30}\b(bug|error|issue|problem)\b",
            r"\b(stacktrace|traceback|stack trace)\b.{0,30}\b(useless|not helpful|confusing|unclear|doesn'?t show)\b",
            r"\b(error|exception|crash)\b.{0,40}\b(no idea|don'?t know|can'?t figure|nowhere near)\b.{0,20}(where|why|what)\b",
            r"\bdebugging\b.{0,40}\b(for (days|hours|weeks)|forever|stuck)\b",
            r"\b(hours|days|weeks)\b.{0,20}\b(debugging|trying to find|looking for)\b",
        ],
        "Debugging for hours, can't locate root cause",
        "atlas finds the structural blast radius; deepstrain can run the diagnosis loop",
        """\
Two things that help when you're stuck like this:

1. **Map where it's actually coming from** — `atlas scan .` builds the call graph \
and shows which functions are structurally riskiest. Sometimes the error source is \
3 layers above where the exception fires. The interactive HTML report makes this \
navigable even in large codebases.

2. **Let an agent try** — `deepstrain eval "find the root cause of this error: <paste error>"` \
runs an autonomous debug loop (reads files, traces calls, checks tests) against your \
local codebase. pip install deepstrain, bring your own DeepSeek key (~$0.01 per run).

What's the error/traceback? Might be able to point you at the likely spot.\
""",
    ),

    # ── atlas: circular imports / dependency hell ─────────────────────────────
    (
        "circular_imports",
        "atlas",
        [
            r"\b(circular|cyclic)\b.{0,20}\b(import|dependency|depend)\b",
            r"\bimportError.{0,30}\b(circular|cannot|cycle)\b",
            r"\bdependency.{0,30}\b(hell|mess|nightmare|loop|cycle)\b",
            r"\b(import|dependency).{0,30}\b(cycle|circular|loop)\b.{0,30}\b(how|fix|solve|resolve|break)\b",
        ],
        "Circular imports / dependency cycle",
        "atlas detects all cycles and shows the exact dependency graph",
        """\
Circular imports in Python usually mean the dependency graph has grown without anyone \
watching it. atlas scan will show you the full dependency map and flag every cycle — \
then you can see exactly which modules are in the loop and where to break it.

```bash
pip install atlas-intel
atlas scan .
```

The report shows a D3 force graph — cycles appear as tightly connected clusters. \
Breaks are usually obvious once you can see the structure visually. \
Fully offline, no cloud, no API key.\
""",
    ),

    # ── deepstrain: need local AI agent for coding ────────────────────────────
    (
        "want_local_ai_agent",
        "deepstrain",
        [
            r"\b(local|offline|self.?hosted)\b.{0,30}\b(llm|ai|agent|assistant|copilot)\b.{0,30}\b(coding|code|dev|engineer)\b",
            r"\b(ai|llm).{0,20}\b(agent|assistant)\b.{0,30}\b(local|my machine|without cloud|privacy|data)\b",
            r"\b(coding assistant|ai agent|llm agent)\b.{0,30}\b(local|self.?host|private|offline)\b",
            r"\bdeepseek\b.{0,40}\b(agent|loop|tool|autonomous|local)\b",
            r"\b(want|need|looking for)\b.{0,30}\b(local|offline)\b.{0,20}\b(copilot|agent|assistant|cursor)\b",
        ],
        "Looking for a local/offline AI coding agent",
        "deepstrain is exactly this: local, bring-your-own-key, 51 tools",
        """\
deepstrain does exactly this — local AI engineering agent, bring your own DeepSeek key \
(stays on your machine, never sent anywhere), 51 built-in tools (file read/write, git, \
grep, test runner, sub-agents).

```bash
pip install deepstrain
deepstrain   # first-run wizard walks through setup
```

Also works with local models via Ollama (set DEEPSTRAIN_BASE_URL=http://localhost:11434/v1). \
If you want to run it headless from another device on your network: \
`deepstrain serve` — it broadcasts as deepstrain.local on mDNS, \
any MCP-compatible AI (Claude Code, etc.) discovers it automatically.\
""",
    ),

    # ── deepstrain: CI keeps failing / tests broken ───────────────────────────
    (
        "ci_failing_tests",
        "deepstrain",
        [
            r"\b(ci|tests?|pipeline)\b.{0,30}\b(failing|broken|keep.?fail|won'?t pass|red)\b.{0,30}\b(can'?t|don'?t|how)\b",
            r"\b(fix|repair|green)\b.{0,30}\b(ci|tests?|build)\b.{0,30}\b(automatically|auto|loop|keep)\b",
            r"\b(tests? keep failing|ci is broken|build is failing)\b",
            r"\b(run tests?|fix tests?|repair tests?)\b.{0,30}\b(automatically|ai|agent|loop)\b",
            r"\b(tests?|ci|build).{0,20}\b(keep|keeps|won'?t|wont|still|always).{0,10}(failing|broken|red|fail)\b",
            r"\b(failing tests?|broken ci|build fail)\b",
        ],
        "CI/tests failing, wants automated fix loop",
        "deepstrain --loop runs tests, fixes failures, reruns until green",
        """\
deepstrain has a `--loop` mode built for exactly this:

```bash
pip install deepstrain
deepstrain eval "run tests, fix all failures, repeat until green" --loop --max-iter 5
```

It runs in your terminal, reads the test output, edits files, reruns — up to N iterations. \
Uses your own DeepSeek key (~$0.009/run). Data never leaves your machine. \
Good for CI pre-push hooks where you want automated repair before the commit.\
""",
    ),

    # ── adauto: built something, no users ────────────────────────────────────
    (
        "built_no_users",
        "adauto",
        [
            r"\b(built|made|created|launched|shipped)\b.{0,40}\b(no (one|users|traction|downloads|installs|views))\b",
            r"\b(indie.?dev|solo.?founder|side.?project)\b.{0,40}\b(marketing|promote|users|traction|growth)\b",
            r"\b(don'?t know how to|no time to|hate)\b.{0,30}\b(market|promote|advertise|social media)\b",
            r"\b(build in public|launch|ship)\b.{0,30}\b(how|tips|advice|help)\b.{0,20}\b(users|traction|attention)\b",
            r"\bonly \d+ (installs?|downloads?|users?|stars?|views?)\b",
            r"\bjust \d+ (installs?|downloads?|users?|stars?|views?)\b",
            r"\b(no one|nobody|0 users|zero users|no users|no downloads|no traction)\b",
            r"\b(side project|indie|solo founder)\b.{0,40}\b(no one|no users|no traction)\b",
        ],
        "Built something but struggling to get attention/users",
        "adauto: give it your repo, it drafts the posts, you approve before anything goes live",
        """\
adauto was built for exactly this situation — you give it your repo and it generates \
platform-specific posts (Reddit, dev.to, Twitter, HN) using your README and features. \
You review and approve each one before anything goes live, so it's not spam. \
The ethics filter blocks anything that looks promotional-first.

```bash
pip install adauto
adauto init-from-repo .     # reads your README + pyproject
adauto generate <name>      # generates drafts
adauto review               # you approve / edit / skip each one
adauto post <name>          # only then does anything post
```

Free tier: 1 campaign, 3 posts/day. What did you build?\
""",
    ),

    # ── Claude / GPT token limit hit — 5-hour wait ────────────────────────────
    (
        "llm_token_limit",
        "deepstrain",
        [
            r"\b(claude|chatgpt|gpt.?4|gpt.?o|gemini|copilot)\b.{0,40}\b(limit|quota|cap|reset|out of|hit the|exceeded|waiting)\b",
            r"\b(token|usage|rate).{0,20}\b(limit|reset|exceed|cap|hit)\b.{0,30}\b(claude|gpt|chatgpt|ai|llm)\b",
            r"\b(wait(ing)?|resett?ing).{0,30}\b(claude|gpt|quota|token|limit|5 hour|5h|reset)\b",
            r"\bclaude.{0,30}(not (working|available|responding)|down|slow|offline)\b",
            r"\b(alternative|alternatives|replacement|instead of|without limit)\b.{0,30}\b(claude|chatgpt|gpt|copilot|ai|llm)\b",
            r"\b(claude|chatgpt|gpt).{0,20}(alternative|replacement|substitute|without (limit|quota))\b",
            r"\b(5 hour|5h|several hours?).{0,20}(wait|reset|before|until)\b",
            r"\b(lost.{0,20}context|context.{0,20}reset|session.{0,20}expired)\b.{0,30}\b(claude|gpt|ai|llm)\b",
        ],
        "Cloud LLM token limit hit, waiting for reset or seeking alternative",
        "deepstrain works locally with Ollama — same tools, no wait, no quota",
        """\
If you're hitting Claude's (or any cloud LLM's) session limit, the reset \
wait is frustrating — especially mid-task when you have context loaded.

**deepstrain** runs fully local with your own key (DeepSeek API, ~$0.009/task) \
or with a local model via Ollama — no session limits, no 5-hour waits, \
your data never leaves your machine.

```bash
pip install deepstrain
deepstrain    # first run: guided setup, get a free DeepSeek key
```

If you already have Ollama: `set DEEPSTRAIN_BASE_URL=http://localhost:11434/v1` \
and it uses your local model instead — zero API cost, zero wait.

What were you working on when the limit hit?\
""",
    ),

    # ── Context window full / lost conversation ───────────────────────────────
    (
        "context_window_full",
        "deepstrain",
        [
            r"\b(context|window|conversation).{0,30}\b(full|too long|limit|maxed|reset|cleared|lost)\b",
            r"\b(lost|losing).{0,20}\b(context|conversation|chat history|progress)\b",
            r"\b(conversation|chat|session).{0,20}\b(too long|too large|maxed out|hit limit)\b",
            r"\b(compac|summarize|compress).{0,20}(context|conversation|chat)\b",
            r"\bcontext.{0,10}(window|limit).{0,20}(coding|project|codebase|files)\b",
        ],
        "Context window too small for the codebase / lost conversation",
        "atlas pack_context sends the right 1400 tokens, not 50k raw files",
        """\
Context window limits hit hardest when the codebase is large — the LLM \
keeps forgetting what it saw 10 messages ago.

Two things that help:

1. **atlas** (`pip install atlas-intel`) — `atlas context "your task"` \
builds a compressed context pack: callers, callees, risk signals, \
~1400 tokens instead of dumping 50k lines of code. The LLM gets \
exactly what it needs for the task.

2. **deepstrain** (`pip install deepstrain`) — runs agent loops locally \
with your own key. Each tool call is fresh context, not accumulated \
conversation history, so it doesn't balloon the way chat sessions do.

How large is your codebase? That might help narrow down which fits better.\
""",
    ),
]


def detect_pain(title: str, body: str) -> list[PainMatch]:
    """
    Run all pain patterns against title + body.
    Returns a list of PainMatch ordered by confidence descending.
    """
    text = f"{title} {body}".lower()
    results: list[PainMatch] = []

    for (pid, product, patterns, summary, hook, template) in _PATTERNS:
        matched_phrases: list[str] = []
        hit_count = 0
        for pat in patterns:
            try:
                m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
                if m:
                    hit_count += 1
                    matched_phrases.append(m.group(0)[:60].strip())
            except re.error:
                pass
        if hit_count == 0:
            continue
        confidence = min(1.0, 0.4 + 0.2 * hit_count)
        results.append(PainMatch(
            pattern_id=pid,
            product=product,
            pain_summary=summary,
            solution_hook=hook,
            response_template=template,
            confidence=confidence,
            matched_phrases=matched_phrases,
        ))

    results.sort(key=lambda x: x.confidence, reverse=True)
    return results


def best_match(title: str, body: str) -> PainMatch | None:
    matches = detect_pain(title, body)
    return matches[0] if matches else None
