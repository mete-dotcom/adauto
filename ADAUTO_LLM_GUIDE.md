# adauto — LLM Integration Guide

## What is adauto?

adauto is a developer marketing automation agent. It generates platform-specific posts
(Reddit, dev.to, Twitter/X) for software products, learns from engagement data, and
adapts future content accordingly.

**Critical constraint:** Posts are NEVER published automatically. Every post requires
explicit human approval before going live.

## Architecture

```
deepstrain (/eval) → content generation
adauto HTTP server → orchestration + approval gate + learning
SQLite (~/.adauto/adauto.db) → posts, metrics, learning data
Campaign TOML (~/.adauto/campaigns/*.toml) → product config
```

## HTTP Server

Default port: **8766**

```bash
curl http://localhost:8766/          # self-description
curl http://localhost:8766/health    # liveness
curl http://localhost:8766/tools     # tool list
```

## Workflow (always in this order)

### 1. Generate posts
```bash
POST /exec {"tool": "generate_post", "args": {"campaign": "deepstrain", "platform": "reddit", "post_type": "showcase"}}
```
→ Returns post content + `post_id` with `status: "pending_approval"`

### 2. Review pending posts
```bash
POST /exec {"tool": "get_pending_approval", "args": {}}
```
→ Returns list of posts waiting for approval

### 3. Approve (or skip)
```bash
POST /approve {"post_id": 42}
POST /approve {"approve_all": true}          # approve all pending
POST /skip {"post_id": 43}
```

### 4. Publish approved posts
```bash
POST /exec {"tool": "run_campaign", "args": {"campaign": "deepstrain"}}
```
→ Only `status=approved` posts are published

### 5. Check engagement (learning)
```bash
POST /exec {"tool": "check_engagement", "args": {}}
```
→ Polls Reddit for upvotes/comments, updates learning data

### 6. View learning scores
```bash
POST /exec {"tool": "score_styles", "args": {"campaign": "deepstrain"}}
```
→ Shows which post_types perform best per platform

## /eval — Natural language agent

```bash
POST /eval {"prompt": "Generate 3 Reddit posts for deepstrain, showcase type"}
POST /eval {"prompt": "What posts are pending approval for code-atlas?"}
POST /eval {"prompt": "How is the deepstrain campaign performing?"}
```

For complex tasks, plan-first is triggered automatically:
```bash
POST /eval {"prompt": "Run a full deepstrain marketing cycle for this week"}
# → Returns plan_id + plan text

POST /eval {"plan_id": "abc123", "approved": true}
# → Executes the approved plan
```

## Available Tools (POST /exec)

| Tool | Args | Description |
|------|------|-------------|
| `list_campaigns` | — | List all configured campaigns |
| `get_stats` | — | Posting statistics by platform/status |
| `get_pending_approval` | campaign?, platform? | Posts waiting for approval |
| `get_approved` | platform? | Approved posts ready to publish |
| `approve_post` | post_id | Approve a specific post |
| `skip_post` | post_id | Skip/reject a specific post |
| `generate_post` | campaign, platform, post_type?, extra_context? | Generate one post |
| `run_campaign` | campaign, platform?, dry_run? | Publish approved posts |
| `check_engagement` | — | Poll platforms for upvote/comment data |
| `score_styles` | campaign? | Show performance scores (learning) |

## Campaign Config (TOML)

Location: `~/.adauto/campaigns/<name>.toml`

```toml
[campaign]
name         = "deepstrain"
product      = "deepstrain"
tagline      = "Local AI engineering agent — 51 tools, plan-first, always-on"
install_cmd  = "pip install deepstrain"
repo_url     = "https://github.com/mete-dotcom/awesome-deepseek-agent"
site_url     = "https://deepstrain.dev"
deepstrain_url = "http://localhost:8765"
enabled      = true

[platforms.reddit]
enabled        = true
posts_per_day  = 0.5
cooldown_hours = 48
post_types     = ["showcase", "tutorial", "question"]
subreddits     = ["LocalLLaMA", "Python", "programming"]
```

## Learning / Adaptive Generation

adauto tracks which posts perform best and injects examples into future prompts.

Score formula: `upvotes + 3×comments` (comments = deeper engagement)

When generating a post, if there are high-performing examples in the DB, the prompt
includes them as few-shot examples:

```
WHAT HAS WORKED WELL (real posts, ranked by engagement):
Example 1 [tutorial] (47 upvotes, 12 comments):
  Title: ...
  Body excerpt: ...
```

This means each campaign improves over time without ML — pure signal loop.

## OS Service

```bash
adauto service install   # register as OS service (auto-starts on boot)
adauto service start     # start now
adauto service stop      # stop
adauto service status    # check
adauto service uninstall # remove
```

The service auto-shuts down after idle timeout (default 1800s).
The OS then restarts it on next activity or on reboot.

## mDNS Discovery

adauto broadcasts as `adauto.local` and `adauto-<hostname>.local` on port 8766.

```bash
adauto beacon --discover   # find other adauto instances on LAN
```
