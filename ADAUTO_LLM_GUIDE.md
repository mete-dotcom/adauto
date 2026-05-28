# adauto — LLM Integration Guide

## What is adauto?

Local developer marketing automation. Runs on user's machine. 
Generates posts, learns from engagement, adapts strategy. 
Human approval required before any post goes live.

**Port: 8766**

## Quick start (3 calls = full cycle)

```
POST /exec {"tool":"run",     "args":{"campaign":"deepstrain"}}
POST /approve {"campaign":"deepstrain"}
POST /exec {"tool":"post",    "args":{"campaign":"deepstrain"}}
```

Done. adauto handled everything else internally.

## GET / (self-description, ~150 tokens)

```bash
curl http://localhost:8766/
```

Returns tool names + descriptions. Read this first if you don't know what campaigns exist.

## 5 Tools

| Tool | Args | What it does |
|------|------|-------------|
| `run` | campaign | Strategy → generate → queue (does NOT post) |
| `status` | — | Pending/approved/posted counts |
| `approve` | post_id OR campaign | Approve for publishing |
| `post` | campaign, dry_run? | Publish approved posts only |
| `report` | campaign? | ROI: cost-per-score, best strategy |

## POST /exec

```bash
curl -X POST http://localhost:8766/exec \
  -H "Content-Type: application/json" \
  -d '{"tool":"run","args":{"campaign":"deepstrain"}}'
```

## POST /approve

```bash
# Approve all pending for a campaign
curl -X POST http://localhost:8766/approve \
  -d '{"campaign":"deepstrain"}'

# Approve specific post
curl -X POST http://localhost:8766/approve \
  -d '{"post_id":42}'
```

## POST /eval (natural language)

```bash
curl -X POST http://localhost:8766/eval \
  -d '{"prompt":"Run the deepstrain campaign"}'
```

For complex multi-step tasks, plan-first is triggered automatically:
```bash
# Step 1 — get plan
curl -X POST http://localhost:8766/eval \
  -d '{"prompt":"Run a full marketing cycle for all campaigns this week"}'
# → {"status":"plan_ready","plan":"...","plan_id":"abc123"}

# Step 2 — execute approved plan
curl -X POST http://localhost:8766/eval \
  -d '{"plan_id":"abc123","approved":true}'
```

## Strategy algorithm (internal — LLMs don't need to know this)

When `run` is called:
1. Check which platforms are due (posts_per_day cooldown)
2. For each due platform:
   - If ≥2 historical posts: **exploit** (use best performing post_type)
   - If new: **explore** (try untried post_types first)
   - Pick subreddit not on cooldown, rank by historical score
3. Generate content via deepstrain /eval (feeds top examples as few-shot)
4. Save as `pending_approval` — NEVER auto-publishes

## Cost tracking

`report` shows:
- `estimated_total_cost_usd` — sum of generation costs
- `cost_per_score_point` — $USD per (upvote + 3×comment)
- `best_strategy` — platform/post_type with lowest cost-per-score

## Campaign config location

`~/.adauto/campaigns/<name>.toml`

Copy from the repo's `campaigns/` directory.

## CLI equivalents

```bash
adauto generate deepstrain     # = run tool
adauto review                  # interactive approval
adauto post deepstrain         # = post tool
adauto check-engagement        # poll for upvotes/comments
adauto benchmark deepstrain    # timing + quality test
adauto service install         # auto-start on boot
adauto license activate <key>  # activate Paddle license
```

## Licensing

Free tier: 1 campaign, 3 posts/day.
Paid: unlimited. Get license at https://adauto.dev

```bash
adauto license activate ADTO-XXXXX-XXXXX-XXXXX-XXXXX
adauto license status
```
