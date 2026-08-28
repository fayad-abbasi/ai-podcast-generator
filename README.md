# AI Podcast Generator

> Two fully automated podcast pipelines sharing one codebase. **AI Industry Weekly** scrapes 18 AI news sources into a public two-speaker podcast. **Substack PM Weekly** turns the maintainer's paid PM newsletters into a private twice-weekly digest with an email companion. Three scheduled runs a week, no human in the loop.

[![CI](https://github.com/fayad-abbasi/ai-podcast-generator/actions/workflows/ci.yml/badge.svg)](https://github.com/fayad-abbasi/ai-podcast-generator/actions/workflows/ci.yml)
[![AI Industry Weekly](https://github.com/fayad-abbasi/ai-podcast-generator/actions/workflows/ai-industry-weekly.yml/badge.svg)](https://github.com/fayad-abbasi/ai-podcast-generator/actions/workflows/ai-industry-weekly.yml)
[![Substack PM Weekly](https://github.com/fayad-abbasi/ai-podcast-generator/actions/workflows/substack-pm-weekly.yml/badge.svg)](https://github.com/fayad-abbasi/ai-podcast-generator/actions/workflows/substack-pm-weekly.yml)

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![Claude API](https://img.shields.io/badge/Claude-Script%20Generation-CC785C?style=flat)](https://anthropic.com)
[![Google TTS](https://img.shields.io/badge/Google%20Cloud-Text--to--Speech-4285F4?style=flat&logo=google-cloud&logoColor=white)](https://cloud.google.com/text-to-speech)
[![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-Automated-2088FF?style=flat&logo=github-actions&logoColor=white)](https://github.com/features/actions)
[![Dependabot](https://img.shields.io/badge/Dependabot-enabled-025E8C?style=flat&logo=dependabot&logoColor=white)](.github/dependabot.yml)
[![CodeQL](https://img.shields.io/badge/CodeQL-scanning-2088FF?style=flat&logo=github&logoColor=white)](https://github.com/fayad-abbasi/ai-podcast-generator/security/code-scanning)
[![Tests](https://img.shields.io/badge/tests-188-success?style=flat&logo=pytest&logoColor=white)](tests/)

---

## The Two Pipelines

| | **AI Industry Weekly** | **Substack PM Weekly** |
|---|---|---|
| **Audience** | Public podcast | Private — maintainer only |
| **Input** | 18 AI news sources (RSS · Atom · sitemap · scrape · API) | Paid Substack PM newsletters, via Gmail API |
| **Cadence** | 1×/week — Wed 8:00 PM ET | **2×/week** — Tue 10:00 PM ET · Fri 2:00 AM ET |
| **Format** | Two-speaker dialogue, ~20 min | Per-newsletter segments + aggregate synthesis |
| **Output** | MP3 + public RSS (`/site`) | MP3 + private RSS (`/site/substack`) **+ HTML digest email** |
| **Extras** | — | Claude-generated **personalized action items** |
| **Dedup strategy** | Snapshot diff on an orphan `snapshots` branch | Gmail message-ID state file + last-run cutoff |
| **Episodes published** | 31 | 29 |

Both pipelines share `summarize` → `scriptgen` → `tts` → `audio` → `publish` and the `Source` plugin protocol. **Only the ingestion stage and the delivery target differ.**

---

## Schedule — 3 Scheduled Runs Per Week

| Workflow | Cron (UTC) | Local (ET) | Frequency |
|---|---|---|---|
| `substack-pm-weekly.yml` | `0 2 * * 3` | Tuesday 10:00 PM | Weekly |
| `substack-pm-weekly.yml` | `0 6 * * 5` | Friday 2:00 AM | Weekly |
| `ai-industry-weekly.yml` | `0 1 * * 4` | Wednesday 8:00 PM | Weekly |
| `ci.yml` | — | on every PR + push to `main` | Per-commit |

All three support `workflow_dispatch` for manual runs.

> **Note on the Substack cadence:** the Tuesday-evening run fires at `02:00 UTC Wednesday`, so GitHub's Actions log labels it Wednesday. Two runs per week, not one.

---

## What It Does

Each run executes a 6-stage pipeline with no human involvement:

1. **Ingests** — RSS, Atom, sitemaps, scrapes and APIs (AI Industry) or the Gmail API (Substack)
2. **Diffs** — snapshot comparison or seen-ID state; only genuinely new content moves forward
3. **Summarizes** with Claude — deduplicates and clusters stories into themes
4. **Generates a script** with Claude — two distinct speaker voices, natural dialogue
5. **Converts to audio** via Google Cloud TTS with ffmpeg stitching
6. **Publishes** — RSS feed on GitHub Pages, plus an HTML digest email for Substack

---

## Pipeline Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                  GitHub Actions — 3 scheduled runs/week          │
└───────────────────────────┬──────────────────────────────────────┘
                            │
        ┌───────────────────┴───────────────────┐
        │                                       │
┌───────▼──────────┐                  ┌─────────▼─────────┐
│  ai_industry.py  │                  │  substack_pm.py   │
│  18 sources:     │                  │  Gmail API →      │
│  RSS·Atom·       │                  │  label Substack/PM│
│  Sitemap·API·    │                  │  → readability    │
│  Scrape          │                  │     extraction    │
└───────┬──────────┘                  └─────────┬─────────┘
        │                                       │
┌───────▼──────────┐                  ┌─────────▼─────────┐
│    diff.py       │                  │ substack_seen.json│
│ orphan snapshot  │                  │ msg-ID dedup +    │
│ branch compare   │                  │ last-run cutoff   │
└───────┬──────────┘                  └─────────┬─────────┘
        │                                       │
        └───────────────────┬───────────────────┘
                            │  ← shared from here down
              ┌─────────────▼─────────────┐
              │       summarize.py        │
              │  Claude — dedupe, cluster │
              │  + aggregate synthesis    │
              └─────────────┬─────────────┘
                            │
              ┌─────────────▼─────────────┐
              │      action_items.py      │
              │  Claude + memory slices   │
              │  (role.md · projects.md)  │
              └─────────────┬─────────────┘
                            │
              ┌─────────────▼─────────────┐
              │       scriptgen.py        │
              │  Claude — two-speaker     │
              │  dialogue                 │
              └─────────────┬─────────────┘
                            │
              ┌─────────────▼─────────────┐
              │    tts.py → audio.py      │
              │  Google TTS (chunked) →   │
              │  ffmpeg stitch w/ gaps    │
              └─────────────┬─────────────┘
                            │
              ┌─────────────▼─────────────┐
              │  publish.py │ email_      │
              │  RSS XML    │ publish.py  │
              │  GH Pages   │ SMTP HTML   │
              └───────────────────────────┘
```

**Sources tracked (18):** Anthropic ×7 (blog, engineering, release notes, Claude Code releases, Python SDK, Models API, docs sitemap) · OpenAI ×6 (blog, changelog, community announcements, release sitemap, Python SDK, status) · Google Gemini ×5 (AI blog, developers blog, Gemini API changelog, Vertex AI release notes, sitemap)

---

## Security & Supply Chain

This repo is public, so the security posture is part of the project.

### Automated dependency management

`.github/dependabot.yml` covers **two ecosystems**, both on a weekly schedule with a 5-PR cap:

| Ecosystem | Directory | Interval | PR limit |
|---|---|---|---|
| `pip` | `/` | weekly | 5 |
| `github-actions` | `/` | weekly | 5 |

**Dependabot security updates are enabled** at the repo level — vulnerability-driven PRs open automatically, independent of the weekly version sweep. **Currently 0 open Dependabot alerts.**

Merged to date: 12 Dependabot PRs across both ecosystems (`lxml`, `markdown`, `feedparser`, `responses`, `google-api-python-client`, `python-dateutil`, `python-dotenv`, `pytest-mock`, `google-cloud-texttospeech`, `actions/checkout` 4→7, `actions/setup-python` 5→7).

### Static analysis

**CodeQL** runs against the Python codebase (`/language:python`) via GitHub's default code-scanning setup — no workflow file to maintain. Three alerts have been triaged and fixed:

| PR | Alert |
|---|---|
| #13 | Clear-text logging of sensitive information |
| #14 | Incomplete URL substring sanitization |
| #15 | Incomplete URL substring sanitization |

### Secret scanning

- **Secret scanning:** enabled
- **Push protection:** enabled — blocks commits containing detected credentials before they land

### Workflow hardening

- **Least-privilege tokens** — `permissions: contents: write` on the publishing workflows, `contents: read` on CI
- **Credentials written to `/tmp`, never the workspace**, and deleted in an `if: always()` cleanup step so they're removed even on failure
- **`timeout-minutes`** on every job (15 / 40 / 10) so a hung run can't burn Actions minutes
- **All secrets injected as env vars** at the step level, never interpolated into shell strings
- **Pinned Python** (3.12) with pip caching
- **Slack alerting on failure** — a webhook post to `#inbox` with a direct link to the failed run, guarded so it no-ops when the secret is absent

---

## Testing & CI

**188 tests across 18 files** (~3,300 lines of test code), run by `ci.yml` on every pull request and every push to `main`.

```bash
pytest -q
```

Coverage spans every stage: ingestion and source adapters, diffing, summarization, script generation (both variants), TTS chunking, audio stitching, RSS publishing, email rendering, the Gmail client, Substack body extraction, and both end-to-end pipeline paths.

Notable: `test_substack_pm_source.py` includes **last-run contract tests** that pin the Gmail cutoff behaviour, added after a bug where the seen-ID append ran past its cutoff.

---

## Key Design Decisions

**Two pipelines, one codebase.** `src/sources/__init__.py` defines a `Source` Protocol and a `ContentItem` TypedDict. Adding a third podcast means writing one `fetch()` method — every downstream stage is already source-agnostic.

**Diff-based ingestion.** Rather than reprocessing everything, AI Industry snapshots the previous run to a standalone **orphan `snapshots` branch** and only forwards new content. `diff.py` reads that baseline with `git show origin/snapshots:snapshots/<source>.json` — the tip blob, never a checkout — so the branch's history carries no value and it is rebuilt from scratch on every run, holding the six JSON snapshots and nothing else. Substack keeps `state/substack_seen.json` with Gmail message IDs plus a last-run timestamp, so a mid-week manual run doesn't re-digest what the scheduled run already sent.

**Two-stage Claude prompting.** Summarization and script generation are separated intentionally. The summarize stage produces structured theme clusters; the script stage consumes those clusters to write dialogue. Combining them in one prompt produced worse scripts.

**Memory slices for personalization.** `action_items.py` loads `prompts/context/role.md` and `projects.md` — a small, hand-maintained slice of the maintainer's actual role and active projects — so the Substack digest's action items are specific rather than generic advice. The real context files are gitignored; `*_sample.md` versions ship as templates.

**Chunked TTS.** Google Cloud TTS caps request size. `tts.py` chunks at a 4,800-byte boundary transparently, then `audio.py` stitches segments with calibrated 400ms speaker gaps.

**Graceful empty weeks.** If ingestion returns zero items or summarization yields zero themes, the run exits `skipped` rather than publishing a hollow episode — and the Substack path sends an explicit "no newsletters this week" email so silence is never ambiguous.

**GitHub Pages as podcast host.** RSS and MP3s live in `/site`, published via Pages. Zero hosting cost, subscribable in any podcast app.

---

## Quick Start

### Prerequisites

- Python 3.12
- ffmpeg (`brew install ffmpeg` on macOS)
- Anthropic API key
- Google Cloud project with Text-to-Speech API enabled
- *(Substack pipeline only)* Gmail OAuth client + a Gmail app password

### Setup

```bash
git clone https://github.com/fayad-abbasi/ai-podcast-generator.git
cd ai-podcast-generator
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
```

### Gmail OAuth (Substack pipeline)

```bash
python scripts/gmail_oauth_bootstrap.py   # one-time — prints the refresh token
```

### Run Locally

```bash
python -m src.pipeline --source ai_industry
python -m src.pipeline --source substack_pm

# Stage-by-stage, for debugging
python scripts/run_local.py --stage ingest --source anthropic_blog
python scripts/run_local.py --stage summarize
python scripts/run_local.py --stage all --dry-run   # No TTS/publish
```

---

## Configuration

### GitHub Actions secrets

| Secret | Used by | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | both | Claude API |
| `GOOGLE_TTS_CREDENTIALS` | both | Base64-encoded GCP service account JSON |
| `GMAIL_OAUTH_CLIENT_ID` | Substack | Gmail API — newsletter ingestion |
| `GMAIL_OAUTH_CLIENT_SECRET` | Substack | Gmail API — newsletter ingestion |
| `GMAIL_OAUTH_REFRESH_TOKEN` | Substack | Gmail API — newsletter ingestion |
| `GMAIL_SENDER` | both | SMTP sender for the digest email |
| `GMAIL_APP_PASSWORD` | both | SMTP app password (not the account password) |
| `NOTIFY_EMAIL` | both | Digest recipient |
| `SLACK_WEBHOOK_INBOX` | both | Failure alerts — optional; the step no-ops if unset |

### Deploy

1. Fork the repo
2. Add the secrets above in **Settings → Secrets → Actions**
3. Enable GitHub Pages from `main`, `/site`
4. Replace `site/cover.jpg` with 3000×3000 podcast artwork
5. Enable Dependabot, CodeQL default setup and secret scanning under **Settings → Code security**
6. Workflows run on their crons — or trigger manually from the Actions tab

---

## Project Structure

```
src/
├── config.py            # 18-source list, model + voice config, both podcasts' settings
├── ingest.py            # RSS / Atom / scrape / sitemap / API fetchers
├── diff.py              # Snapshot loading, saving, comparison
├── summarize.py         # Claude — dedupe, cluster, per-newsletter + aggregate
├── action_items.py      # Claude — personalized action items from memory slices
├── scriptgen.py         # Claude — two-speaker script (both variants)
├── tts.py               # Google Cloud TTS with chunking
├── audio.py             # ffmpeg stitching with silence gaps
├── publish.py           # RSS XML manipulation
├── email_publish.py     # SMTP HTML digest email
├── _claude_response.py  # Text-block extraction, thinking-setting agnostic
├── pipeline.py          # Orchestrator — dispatches by --source
└── sources/
    ├── __init__.py      # Source Protocol + ContentItem TypedDict
    ├── ai_industry.py   # 18-source adapter
    ├── substack_pm.py   # Gmail-backed adapter + seen-ID state
    ├── _gmail_client.py # Gmail API wrapper
    └── _substack_body.py# readability-based post extraction
prompts/
├── summarize.txt · scriptgen.txt
├── summarize_substack.txt · scriptgen_substack.txt · aggregate_substack.txt
├── action_items.txt
└── context/             # role.md + projects.md — gitignored, *_sample.md shipped
templates/feed_template.xml
state/substack_seen.json # Gmail dedup state
specs/                   # Spec-driven build docs for the Substack pipeline
tests/                   # 188 tests, 18 files
scripts/
├── run_local.py             # Stage-by-stage local runner
└── gmail_oauth_bootstrap.py # One-time OAuth token generation
site/                    # GitHub Pages — public feed + /substack private feed
.github/
├── dependabot.yml       # pip + github-actions, weekly
└── workflows/           # ci.yml · ai-industry-weekly.yml · substack-pm-weekly.yml
```

---

## Operational Notes

**Reliability.** Substack PM Weekly: 8 of the last 8 scheduled runs succeeded. AI Industry Weekly: one failure on 2026-08-27, root-caused and fixed the same day (below).

**The `anthropic` 1.1.0 incident (Aug 2026).** `anthropic` 1.1.0 removed `temperature` from `Messages.create()`. The unpinned `>=0.42.0` floor pulled it onto a fresh Actions runner and broke the scheduled pipelines — the classic "worked yesterday, fresh runner today" failure. Fix: pin `anthropic>=1.1.0,<1.2.0` (a *minor*-level ceiling, since the break shipped in a minor bump) and remove `temperature=` from all call sites. The `SUMMARIZE_TEMPERATURE` / `SCRIPTGEN_TEMPERATURE` constants remain in `config.py` with the call sites commented rather than deleted, documenting what the values were.

**Push contention.** Both publishing workflows retry `git push` three times with a 30s backoff — episode commits race with Dependabot merges on a shared `main`.

**`git add -f` is deliberate.** `.gitignore` excludes `*.mp3` to keep local scratch files out; published episodes are force-added by the workflows.

**Claude model.** `claude-sonnet-5`, set in `config.py:CLAUDE_MODEL`.

**Thinking is disabled explicitly.** On Sonnet 4.6 omitting the `thinking` parameter meant no thinking; on Sonnet 5 it is **on by default**, which makes `content[0]` a thinking block rather than the text — and with `display` defaulting to `"omitted"`, that block is an empty string. `config.py` therefore sets `CLAUDE_THINKING = {"type": "disabled"}` so output shape and token spend match the behaviour the prompts were tuned against. `src/_claude_response.py` selects the text block **by type rather than position**, so flipping thinking to `{"type": "adaptive"}` is a safe one-line opt-in.

**Cost.** Roughly **$0.08 per episode** (Claude API + Google TTS); GitHub Pages and Actions are free at this volume. This figure is an original estimate from the AI Industry build and has not been re-measured since the Substack pipeline and action-items stage were added.

---

## Roadmap

- [ ] Re-measure per-episode cost across both pipelines
- [ ] Revisit the `anthropic<1.2.0` ceiling once 1.2.x is validated
- [ ] Evaluate adaptive thinking (`CLAUDE_THINKING`) against summary quality and cost
- [ ] Per-source relevance scoring to filter low-signal content
- [ ] Dynamic episode length based on news volume that week
- [ ] Chapter markers in the RSS feed for navigation
- [ ] Web player embedded in GitHub Pages

---

## Why I Built This

I wanted to understand what a production-grade, multi-stage AI pipeline actually looks like end to end — not a demo with a single API call, but something with real ingestion, diffing, multi-prompt chaining, audio processing, automated deployment, and the unglamorous operational surface that comes with running on a schedule: dependency drift, supply-chain scanning, failure alerting, and state that has to survive between runs.

The prompt engineering for `scriptgen.py` was the most interesting problem — getting Claude to write dialogue that sounds like two distinct people talking, not a formatted article read aloud. The most *instructive* problem was the `anthropic` 1.1.0 break: a pipeline that runs unattended fails in ways a demo never does.

---

## Related Projects

- [codeguard-ai](https://github.com/fayad-abbasi/codeguard-ai) — AI-powered PR review bot using Claude + GitHub webhooks
- [OpenClaw (Privacy-First)](https://github.com/fayad-abbasi/My-privacy-first-OpenClaw-Implementation) — Self-hosted AI assistant on Raspberry Pi

---

## License

MIT — fork it, extend it, point it at different sources.

---

<div align="center">
  <sub>Built by <a href="https://linkedin.com/in/fayad-abbasi">Fayad Abbasi</a> · DevEx PM exploring production AI pipelines</sub>
</div>
