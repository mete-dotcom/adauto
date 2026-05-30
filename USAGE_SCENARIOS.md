# DEEPSTRAIN ECOSYSTEM — Comprehensive Usage Scenarios & Marketing Reference

> **Purpose.** This is the canonical reference for every way the three products
> (**atlas**, **deepstrain**, **adauto**) are used — alone and in combination,
> from the most basic to the most complex.
>
> **For adauto / marketing:** This document is the *source of truth* for marketing
> claims. Every scenario carries a **claim-status marker**. adauto may only post
> claims marked ✅ **VERIFIED**. 🔶 **INTERNAL ESTIMATE** needs a disclaimer or
> re-measurement before use. 🟦 **ROADMAP** must never be stated as a present-tense
> fact. The ethics filter must enforce this.

**Last updated:** 2026-05-30
**Verified against:** HOS Alive (real 388-file / 111,581-line FastAPI trading platform)

---

## Claim-Status Legend

| Marker | Meaning | adauto rule |
|--------|---------|-------------|
| ✅ VERIFIED | Measured on a real codebase in this repo's testing | Post freely with the number |
| 🔶 INTERNAL ESTIMATE | From internal config / single observation, not independently reproduced | Needs "approximately" + may not generalize |
| 🟦 ROADMAP | Designed/partially built, not shippable today | Never present-tense. Use "coming" or omit |

---

## Product Identities (marketing one-liners)

| Product | PyPI | Tagline | Lifecycle phase | Tiers (USD/mo) |
|---------|------|---------|-----------------|----------------|
| **atlas** | `pycode-atlas` | *Deterministic code intelligence — no LLM, offline, zero tokens.* | UNDERSTAND / VERIFY | free · solo $19 · pro $49 · enterprise |
| **deepstrain** | `deepstrain` | *Terminal-native AI engineering agent — cheap, fast, obsessive.* | BUILD / FIX | standard $9 · pro $29 |
| **adauto** | `adauto` | *Developer marketing automation — ethics-filtered, human-approved.* | DISTRIBUTE | free · solo · pro |
| **Bundle** | — | *The Cognition Stack: build with AI, understand what you built, debug when it breaks.* | ALL | $46/mo (atlas pro + deepstrain standard, ~20% off) |

---

## The 5 Axes (coordinate system)

Every scenario is a point in this space:

```
1. ENGINE (deepstrain)  : none → DeepSeek API → local DeepSeek → local Qwen Coder → any OpenAI-compatible
2. ORCHESTRATOR         : human-CLI → user's-own-LLM (MCP) → scheduled/CI → autonomous-loop → team-mesh
3. TIER                 : free → solo/standard → pro → enterprise → bundle
4. DEPLOYMENT           : standalone-CLI → stdio-MCP → HTTP-server → OS-service → CI → LAN-mesh → air-gapped
5. LIFECYCLE            : BUILD → MAP → VERIFY → REFACTOR → GUARD → DISTRIBUTE → MONITOR
```

The defining strategy: **the user's own trusted LLM becomes the salesperson.** Our
products plug into it via MCP, deliver value *before activation* (the "shock moment"),
and self-describe through the **cognition envelope** so the assistant relays both the
value and the contextual recommendation — in the user's own words, at the moment of need.

---

## PROOF POINTS — Marketing Ammunition (verified numbers)

These are measured facts adauto can cite. Source = HOS Alive unless noted.

| # | Claim | Number | Status |
|---|-------|--------|--------|
| P1 | atlas full scan of a 388-file / 111k-line project | **69s, 1999 functions, 29,148 edges, health 89/100** | ✅ VERIFIED |
| P2 | atlas scan token cost | **0 LLM tokens** (deterministic, offline) | ✅ VERIFIED |
| P3 | `atlas verify` eliminates static dead-code false positives | **33 rescued, 1544 confirmed dead** (single run) | ✅ VERIFIED |
| P4 | deepstrain `strain_project` full stack+map | **0.7s, no LLM, 0 tokens** | ✅ VERIFIED |
| P5 | atlas security scan | **Bandit-backed, runs inside the scan** | ✅ VERIFIED |
| P6 | deepstrain engine is pluggable | DeepSeek API / local DeepSeek / local Qwen Coder | ✅ VERIFIED (API path tested; local = supported config) |
| P7 | deepstrain avg task cost | **~$0.009 / task (DeepSeek-V3)** | 🔶 INTERNAL ESTIMATE |
| P8 | adauto cost per post | **~$0.00034 / post** | 🔶 INTERNAL ESTIMATE |
| P9 | Fully local / air-gapped cognition stack | local Qwen + offline atlas = zero cloud bytes | 🟦 ROADMAP (capability exists, not end-to-end validated) |
| P10 | LAN auto-discovery via mDNS | broadcasts `_mcp._tcp.local.` + `_deepstrain._tcp.local.` as `deepstrain.local:<port>` | ✅ VERIFIED (broadcast + peer registry + mesh routing code shipping) |
| P11 | One install, reachable from every machine on the LAN | `deepstrain.local` — no IP config | 🔶 INTERNAL ESTIMATE (zero-config pickup depends on the MCP client supporting mDNS browse) |

> **adauto rule:** Lead with P1–P5 (verified). Use P7/P8 only with "approximately".
> Never headline P9 as shipping.

---

# PART B — SCENARIO LADDER (deepened)

Each scenario: **context · pain · flow (commands + expected output) · cost · value · marketing angle · channel · CTA.**

---

## L0 — Zero commitment: install, try, no token, no license

### 0.1 — atlas first scan  ✅ VERIFIED
- **Persona:** vibe coder who inherited / AI-generated a codebase they don't understand.
- **Pain:** "I have 10k lines I didn't fully write and no idea what's in here."
- **Flow:**
  ```
  $ pip install pycode-atlas
  $ atlas scan .
  ```
  **Expected output:**
  ```
  Scan Summary
  Files 384 · Functions 1999 · Duration 69.13s · Health 89/100
  Report: atlas_report.html
  ```
- **Cost:** $0, 0 tokens, no account, no cloud.
- **Value:** Full architectural map in ~70s. The interactive HTML graph is the "go quiet" moment.
- **Marketing angle:** *"I ran one command on a 100k-line AI-generated app. 70 seconds later I understood it. No LLM, no cloud, 0 tokens."*
- **Channel:** r/Python, Show HN, X thread w/ graph screenshot.
- **CTA:** `pip install pycode-atlas`

### 0.2 — deepstrain deterministic tool (no engine)  ✅ VERIFIED
- **Pain:** "I want to understand a repo's stack without burning my LLM tokens."
- **Flow:**
  ```
  $ pip install deepstrain
  $ deepstrain exec strain_project
  ```
  **Expected output (0.7s):** stack detection (FastAPI/React/Mongo/Redis/RQ/JWT), full directory map with LOC, cycle analysis ("No circular dependencies, 197 modules"), code-style + naming inference, dead-code list with file:line.
- **Cost:** $0, **no LLM at all.**
- **Value:** Instant onboarding to an unfamiliar codebase.
- **Marketing angle:** *"deepstrain mapped my whole stack in 0.7 seconds — without calling any LLM. Zero tokens."*
- **Channel:** r/LocalLLaMA, r/Python.
- **CTA:** `deepstrain exec strain_project`

### 0.3 — adauto signal scan (free)  ✅ VERIFIED (free tier limits enforced)
- **Pain:** "I don't know where my dev audience is hurting."
- **Flow:** `adauto init` → `adauto pulse` (free: 1 campaign, 3 posts/day).
- **Value:** Surfaces pain points / discussions to engage with.
- **Marketing angle:** *"adauto found where developers are actually asking for what I built."*
- **CTA:** `pip install adauto`

---

## L1 — Single product, full power (activated + engine choice)

### 1.1 — atlas runtime verification (`atlas verify`)  ✅ VERIFIED
- **Pain:** "Static dead-code tools cry wolf — they flag my FastAPI routes and tests as dead."
- **Flow:**
  ```
  $ atlas scan .
  $ atlas verify --run lifecycle_simulation.py
  ```
  **Expected output:**
  ```
  Rescued (false dead) 33  ·  Confirmed dead 1544  ·  Runtime-only edges 17
  ✓ 33 false positive(s) eliminated — statically 'dead' but proven alive at runtime
  ```
- **Value:** The only dead-code report you can trust — static *prediction* upgraded to runtime *proof*. (Lineage: the `trading_guardian` prototype.)
- **Marketing angle:** *"Every dead-code tool lies. atlas runs your code and proves what's actually dead — 33 false positives gone in one run."*
- **Channel:** Show HN (strong technical hook), r/Python.
- **CTA:** `atlas verify --run <script>`

### 1.2 — deepstrain engine permutations (same task, 3 brains)  ✅ VERIFIED (engine-agnostic design)
- **Pain:** "I want an AI coder but (a) cheap, or (b) private, or (c) air-gapped."
- **Flow:**
  ```
  $ deepstrain configure        # choose engine
     (a) DeepSeek API     → fastest, cloud, ~$0.009/task 🔶
     (b) local DeepSeek   → $0/task, private, needs GPU
     (c) local Qwen Coder → $0/task, air-gapped, code-specialized
  $ deepstrain eval "add retry logic to all DB calls"
  ```
- **Value:** Capability portability on the *engine* axis — the principle is identical regardless of brain. Bank → air-gapped Qwen; solo founder → cheap API.
- **Marketing angle:** *"Same agent. Your choice of brain: DeepSeek API, local DeepSeek, or local Qwen Coder. Cheap, private, or air-gapped — you pick."*
- **Channel:** r/LocalLLaMA (perfect fit), r/selfhosted.
- **CTA:** `deepstrain configure`

### 1.3 — adauto multi-campaign  ✅ VERIFIED (config exists)
- **Note for adauto:** Your own campaign configs (`campaigns/deepstrain.toml`, `campaigns/code-atlas.toml`) already market atlas & deepstrain. **The ecosystem markets itself.** Use this as a meta-angle: *"this post was drafted by adauto, the tool it's describing."*

---

## L2 — Plug into the user's OWN LLM via MCP (shock + self-advertising)

### 2.1 — atlas inside Claude / Cursor  ✅ VERIFIED (envelope wired)
- **Flow:**
  ```
  $ atlas mcp --project .          # stdio for Claude Desktop / Cursor
  ```
  User asks their LLM: *"any dead code in this project?"*
  ```
  LLM → atlas.dead_code()
  atlas → cognition envelope:
  {
    "result": { "count": 1577, "dead_code": [...] },
    "attribution": { "benefit": "deterministic · offline · 0 LLM tokens" },
    "tier": "free",
    "recommendation": {
      "product": "atlas pro",
      "pitch": "This list is static — routes/tests are false positives. atlas verify
                ran your code and rescued 33 wrongly-flagged functions.",
      "cta": "atlas verify --run <script>", "optional": true
    }
  }
  ```
  The user's LLM then says, in its own words: *"Found 1577 candidates (atlas, 0 tokens). Some are framework routes — possibly false positives. We can run `atlas verify` to confirm what's truly dead."*
- **Value:** The recommendation arrives from the assistant the user already trusts, exactly when relevant. **Customer acquisition cost ≈ 0.**
- **Marketing angle:** *"Your AI assistant will tell you to buy atlas — because it can feel the difference. Plug atlas into Claude/Cursor and watch."*
- **Channel:** X (devtool crowd), r/ChatGPT, r/cursor.
- **CTA:** `atlas mcp`

### 2.2 — deepstrain as the user's LLM's "cheap hands"  ✅ VERIFIED (envelope wired in module; MCP wiring pending 🔶)
- **Pain:** "My main assistant burns its context/quota doing repetitive edits across 15 files."
- **Flow:** `deepstrain mcp` → user asks their LLM *"standardize logging across these 15 files"* → the LLM delegates the heavy, repetitive edits to `deepstrain.eval` (cheap DeepSeek) → envelope: *"8 turns · ~$0.009 DeepSeek · your primary assistant's quota untouched."*
- **Value:** This is the original **"Flash orchestrates, DeepSeek executes"** model, delivered through MCP. The expensive orchestrator offloads grunt work to the cheap obsessive executor.
- **Marketing angle:** *"Stop burning your premium LLM on grunt work. deepstrain does the obsessive edits for ~a cent, so your main assistant stays sharp."*
- **Channel:** X, r/LocalLLaMA.
- **CTA:** `deepstrain mcp`

### 2.3 — `deepstrain inject`  ✅ VERIFIED (command exists)
- **Flow:** `deepstrain inject` adds a self-introduction to `CLAUDE.md` → the user's LLM knows from the first message that deepstrain exists and when to use it.
- **Value:** Zero-friction discovery inside the user's existing AI workflow.

---

## L3 — Pairwise combinations (deepened)

### 3.1 — atlas → deepstrain (zero-waste engineering) — FLAGSHIP  ✅ VERIFIED (each half) 🔶 (combined flow)
- **Pain:** "Refactoring blind is terrifying — I don't know what I'll break."
- **Flow:**
  ```
  1. atlas mcp + deepstrain mcp both connected to the user's LLM
  2. User: "ProcessTradeOpenHandler is too complex, refactor it"
  3. LLM → atlas.simulate_change("ProcessTradeOpenHandler")        # blast radius, 0 tokens
  4. atlas → "47 nodes affected, 3 critical intersections" + envelope: fix → deepstrain
  5. LLM → deepstrain.eval("refactor X, preserve these 47 contracts")
  6. deepstrain edits → atlas verify confirms nothing went dead/broke
  ```
- **Value:** atlas predicts the risk (no tokens), deepstrain executes with a map instead of guessing. **Map, then move.**
- **Marketing angle:** *"atlas tells you what a change will break — before you touch it. deepstrain makes the change safely. Refactor with a map, not a prayer."*
- **Channel:** Show HN, X thread (step-by-step).
- **CTA:** Bundle — `the cognition stack`

### 3.2 — atlas → adauto (the launch / investor story)  🔶
- **Flow:** `atlas export` → portable artifact (health 89/100, risk map, `graph.json` + `insights.json` + `context.md` + `index.html`) → adauto drafts a "codebase health 89/100, 0 circular deps" launch/credibility post.
- **Marketing angle:** *"Before you pitch investors: do you know your codebase health score? Mine is 89/100 — here's the report."*

### 3.3 — deepstrain → adauto (build → ship)  🔶
- **Flow:** deepstrain writes a feature → adauto drafts the "new feature" announcement for 3 platforms (ethics-filtered, awaits human approval).

---

## L4 — All three, sequential: full lifecycle  🔶 (sequence is real; end-to-end timing is illustrative)

```
deepstrain (BUILD) → atlas (MAP+VERIFY) → deepstrain (FIX) → atlas (GUARD) → adauto (DISTRIBUTE)
```

### 4.1 — Solo founder, zero → launch (illustrative 1-week arc)
- Day 1–3: `deepstrain eval` builds the MVP (local Qwen, $0).
- Day 4: `atlas scan` + `atlas verify` → 89/100, clears 33 real dead functions.
- Day 5: `atlas` commit_guard → architecture guard in CI.
- Day 6: `adauto` drafts Show HN + r/Python posts.
- Day 7: launch.
- **Marketing angle:** *"One week, one person, three tools: built it, understood it, shipped it."* (mark as illustrative)

---

## L5 — MCP Mesh: the recommendation network drives the journey  🔶 (envelopes verified; full mesh wiring partial)

### 5.1 — Full orchestra
All three MCP servers connected. User: *"turn this side-project idea into something real."*
```
LLM → deepstrain scaffolds code
    → envelope: "understand → atlas"
LLM → atlas maps it, surfaces risk
    → envelope: "fix → deepstrain"
LLM → deepstrain hardens it
    → envelope: "launch → adauto"
LLM → "Looks ready. Want to announce it? adauto can draft posts…"
```
- **Value:** Three sales, one conversation, all from the trusted assistant — the user never searched for a product name.
- **Marketing angle:** *"You bring the idea and your favorite AI. The tools introduce themselves exactly when you need them."*

---

## L6 — Engine + deployment permutations (enterprise / cowork)

### 6.1 — Fully local, zero-cloud cognition stack  🟦 ROADMAP
- **Flow:** deepstrain (local Qwen Coder) + atlas (already offline) + air-gapped network → no byte leaves the machine.
- **Persona:** bank / defense / healthcare.
- **Value:** atlas's "no LLM, offline, deterministic" + deepstrain's local engine = auditable, provable privacy.
- **adauto rule:** Capability exists but end-to-end air-gapped validation is pending → market as *"designed for air-gapped"*, not *"runs air-gapped today"*.

### 6.2 — CI/CD integration  ✅ VERIFIED (workflows exist) 🔶 (gating behavior)
- **Flow:** `.github/workflows` runs `atlas mcp` + `commit_guard`; a PR that introduces an architecture violation / new dead code / risk spike is flagged.
- **Marketing angle:** *"A reviewer that reads the whole call graph on every PR — deterministically, in seconds."*
- **Channel:** r/devops, dev.to.

### 6.3 — LAN mesh (beacon / mDNS)  🔶
- **Flow:** `atlas beacon` + `deepstrain mesh` → teammates on the same network discover instances; shared license via env var (cowork).

### 6.4 — deepstrain as an OS service  ✅ VERIFIED (command exists)
- **Flow:** `deepstrain service install` → runs in the background, IDE-independent.

### 6.5 — Ambient cross-device mesh — *"wait, which computer did I even install it on?!"*  ✅ VERIFIED (mesh code) · 🔶 (fully-automatic pickup)
- **Persona:** developer with more than one machine on the same network — a desktop + a laptop, or an always-on home/office box.
- **The effect (the wow moment):** You installed a product on **Computer A** and left it running. Days later, on **Computer B**, you give your local LLM a task — and notice it's using deepstrain (or atlas, or adauto) and the result is dramatically better. You think: *"hang on… which machine did I even install this on?"* The tool followed you across the network.
- **How it actually works (real):**
  ```
  Computer A:  $ deepstrain serve          # or: atlas serve / adauto serve
               → mDNS broadcast:
                 http://deepstrain.local:8765/eval
                 http://deepstrain-<hostname>.local:8765/eval
                 http://<ip>:8765/eval   (direct fallback)
  Computer B:  MCP client resolves deepstrain.local → uses the A instance
  ```
  - Each product advertises over **mDNS/Bonjour**. deepstrain registers both
    `_mcp._tcp.local.` (the *standard* MCP discovery type) and a
    `_deepstrain._tcp.local.` fallback, with properties (label, tier, tool count,
    version, role, eval URL). `mesh.py` keeps a live peer registry and can route
    tool calls to a **specialized satellite** (e.g. a GPU box that handles
    `execute`/`write`, set via `[mesh] role = "satellite"`).
  - atlas has the same idea via `atlas beacon` (broadcast/discover on the LAN);
    adauto broadcasts via `start_beacon` (disable with `--no-mdns`).
- **Value:** Install once, reach it from anywhere on your network — no IP wrangling,
  no per-machine reinstall. A heavy always-on node (GPU + local Qwen) serves every
  thin client around it. This is **capability portability on the *location* axis**:
  the capability is no longer bound to the device you typed the command on.
- **Honest claim status:**
  - ✅ The broadcast + peer discovery + mesh routing is **real, shipping code**.
  - 🔶 The *fully-automatic, zero-config* pickup depends on the MCP client supporting
    mDNS browsing. Today you typically point the client at `deepstrain.local:<port>`
    **once**; after that it "just works" across reboots and IP changes.
- **Marketing angle (honest framing):** *"Run it on one machine. Reach it from every
  machine on your network — `deepstrain.local`, no IP, no reinstall. The always-on box
  does the heavy lifting; your laptop just asks."* The *"which computer did I install
  it on?!"* line is a great **organic testimonial**, not a spec claim — present it as
  a user's lived experience, never as guaranteed auto-discovery on every client.
- **Channel:** r/selfhosted, r/homelab, r/LocalLLaMA (this crowd loves LAN mesh + always-on GPU node stories).
- **CTA:** `deepstrain serve` on your always-on machine.

---

## L7 — Autonomous loops  🟦 ROADMAP

### 7.1 — Self-improving loop
`atlas verify` in a loop + deepstrain agent fixes failures + adauto drafts a changelog post on every green build.

### 7.2 — Continuous architecture watch
`live_watch` (enterprise) watches file changes → re-scans on each save → alerts on architectural drift instantly.

- **adauto rule:** Both are roadmap. Never claim "self-driving" as present-tense.

---

## L8 — Team / multi-user (cowork layer)  🟦 ROADMAP (single-user works today)

### 8.1 — Shared capability token
Env var lets the whole team share one tier. `atlas export` artifact is attached to a PR and opens 5 years later (portable, self-contained).
- **Status today:** licenses are per-machine (`~/.atlas`, `~/.deepstrain`, `~/.adauto`). Shared-token cowork is designed, not shipped.

---

## L9 — Platform / embedded  🔶

### 9.1 — All three in HTTP-server mode
`deepstrain serve` + `atlas serve --http` + `adauto serve` behind your own product → embed a "cognition" layer into your tool.

---

# PART C — Persona Journeys

| Persona | Entry | Engine | Orchestrator | Peak scenario | Buys |
|---------|-------|--------|--------------|---------------|------|
| Vibe coder / solo | atlas scan (free) | DeepSeek API | own LLM (Cursor) | L5 mesh | bundle |
| AI-assisted dev | deepstrain exec | local DeepSeek | MCP + CLI | L3.1 zero-waste | deepstrain pro |
| Small team (2–5) | atlas + commit_guard | DeepSeek API | CI + MCP | L6.2 + L8 | atlas pro |
| Enterprise | atlas (offline) | local Qwen (air-gap) | OS service + CI | L6.1 fully local | enterprise |
| Indie maker | three (bundle) | DeepSeek API | autonomous | L7.1 self-driving | bundle |

---

# PART D — Combination Matrix

```
                atlas        deepstrain     adauto
  atlas          —           map → fix      audit → market
  deepstrain   build → map     —            build → ship
  adauto      market → audit  ship → build    —

  ALL THREE: build → map → verify → fix → guard → distribute → monitor
  BUNDLE: the cognition stack (atlas pro + deepstrain) = $46/mo
```

---

# PART E — Marketing Extraction Guide (for adauto)

**How to turn a scenario into a post:**
1. Pick a scenario. Read its **claim-status marker**. If 🟦 ROADMAP → skip or phrase as "coming".
2. Structure: **Pain → one-command demo → measured proof (from PROOF POINTS) → CTA.**
3. Always cite a real number from PROOF POINTS (P1–P5 preferred). Never invent metrics.
4. Match the channel (below). Respect each platform's culture.

**Channel map:**

| Scenario theme | Best channels |
|----------------|---------------|
| "Understand AI-generated code" (L0.1, L1.1) | Show HN, r/Python, X |
| "Local / private / air-gapped" (L1.2, L6.1) | r/LocalLLaMA, r/selfhosted |
| "Your LLM recommends it" (L2.x, L5) | X, r/ChatGPT, r/cursor |
| "Refactor safely / blast radius" (L3.1) | Show HN, dev.to |
| "PR reviewer / CI" (L6.2) | r/devops, dev.to |
| "Ambient cross-device mesh" (L6.5) | r/selfhosted, r/homelab, r/LocalLLaMA |

**Tone discipline (hard rules — enforce in ethics filter):**
- Lead with verified numbers (P1–P5). Mark estimates (P7/P8) with "approximately".
- Never present 🟦 ROADMAP as shipping.
- No superlatives without a number behind them.
- The cognition envelope's recommendations are *optional and contextual* — marketing copy should mirror that restraint. We sell by being demonstrably useful, not loud.

**The implicit universal-usefulness angle (never name the architecture):**

All three products share a portable, engine- and relation-agnostic design — that
is *why* they stay useful in any setup. But **never name the architecture** in
marketing. "Capability portability", "relation-agnostic", "deterministic
primitive", "cognition envelope" are internal engineering terms — they *explain*
instead of *sell*, and they make a simple, safe purchase sound complicated.

Instead, make the reader **feel the conclusion** the architecture produces:
> *"This will help me no matter what — so buying it is never a wasted bet."*

Show it, don't name it (examples):
- "Works with the LLM you already use." → (engine/relation-agnostic, implied)
- "Runs where your code runs — laptop, server, air-gapped box." → (portable, implied)
- "One tool. Every project, every stack, every workflow." → (universal, implied)
- "Whatever you build next, it's already useful." → (future-proof, implied)
- "Plugs into what you already have. No lock-in, no setup tax." → (agnostic, implied)

The target thought in the reader's head: *"I'll buy it — it'll be useful to me
no matter what."* That feeling is the conversion. The architecture is the reason
it's true; the copy never has to say the reason.

**Forbidden in copy (jargon ban):** `capability portability`,
`relation-agnostic`, `location-agnostic`, `deterministic primitive`,
`cognition envelope`, `capability mesh`. Enforce in the ethics/style filter.

**The meta-story (adauto's strongest, most honest angle):**
> *"This post was drafted by adauto — one of the three tools it describes. The
> ecosystem markets itself, ethically, with numbers it can prove."*

---

*End of reference. Keep PROOF POINTS in sync with the latest measurements before any campaign.*
