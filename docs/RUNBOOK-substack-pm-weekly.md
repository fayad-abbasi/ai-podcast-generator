# Runbook — Substack PM Weekly

## Cadence

Two scheduled runs a week, plus manual dispatch:

| Cron | UTC | Eastern |
|---|---|---|
| `0 2 * * 3` | Wed 02:00 | Tue evening |
| `0 6 * * 5` | Fri 06:00 | Fri 02:00 |

Lookback is **7 days** (`SUBSTACK_LOOKBACK_DAYS`), capped at **10 newsletters per run**
(`SUBSTACK_MAX_NEWSLETTERS_PER_RUN`, keeps the newest and drops the rest).

---

## ⚠️ Language: there is no "fixed"

A change is **deployed**. It is not fixed until a real run proves it.

This pipeline has been falsely declared fixed three times — 2026-03-20, 2026-04-18,
and 2026-09-07 — each time on the strength of something other than a passing
scheduled run. Tests passing is not proof. A green CI is not proof. **A green
scheduled or dispatched run of the actual workflow is proof.**

Until then the status is: *fix deployed, awaiting verification.*

---

## When a run fails

### 1. Diff before code

Do this **first**, before reading a single line of source. It is what actually
cracked the September failure, and it was tried fifth.

```bash
gh run list --repo fayad-abbasi/ai-podcast-generator --workflow "Substack PM Weekly" --limit 15
```

Find the **last success** and the **first failure**. Then look at what landed between:

```bash
git log --since=<last-good-date> --until=<first-bad-date> --date=short --pretty="%ad %h %s"
```

Dependency bumps and model changes are the usual culprits. The September break was
`#23`, which moved `CLAUDE_MODEL` from `claude-sonnet-4-6` to `claude-sonnet-5`;
nobody connected it for a week.

### 2. Count the failures

One failure is an incident. Three identical failures is a *pattern*, and it means
any fix shipped in between did not work.

```bash
gh run view <run-id> --repo fayad-abbasi/ai-podcast-generator --log-failed | grep -iE "rejected|Invalid |truncated|WARNING"
```

### 3. Read what is *absent*, not just what is present

The September misdiagnosis turned on this. The logs showed
`Invalid aggregate_summarize output — retrying` but contained **no**
`Aggregate summary rejected:` line. Callers guard with
`if parsed and _validate(...)`, so a missing rejection line means
**parsing failed and validation never ran** — a different layer entirely.

A fix aimed at validation could never have worked, and didn't.

### 4. Read the failure report

Since #33, a failed run writes `diagnostics/failure-*.json` and emails it. It
contains the full unparseable response, the reason *every* parse strategy
rejected it, the model config, and the traceback. It is also uploaded as a
workflow artifact (`failure-report-<run-id>`, 30-day retention).

If that report exists, steps 1–3 are usually unnecessary.

### 5. Reproduce before fixing

**Do not ship a fix you have not watched fail.** Take the raw response out of the
report and run it through the failing function in isolation. If it does not
reproduce, the diagnosis is a theory.

### 6. Turn the failure into a fixture

Copy the captured response into `tests/fixtures/` and write a regression test that
replays it. The parser tests previously used only tidy synthetic inputs
(`'{"a": 1}'`, `"not json"`), which is precisely why nothing caught real model
output containing literal newlines.

**Every fix ships with the test that would have caught it.**

---

## Verifying a dependency bump

⚠️ **Dependabot merges are not free.** This pipeline has been broken by a dependency
change twice:

- **anthropic 1.1.0** removed `temperature` from `Messages.create()` and broke the
  scheduled runs. Fixed by removing `temperature=` from all three call sites and
  pinning `<1.2.0` — the ceiling is minor-level *because this package ships
  breaking changes in minor bumps*.
- **`#23`** moved `CLAUDE_MODEL` to `claude-sonnet-5`, which changed output
  formatting and broke JSON parsing for a week before anyone connected it.

Neither was caught before a scheduled run failed. **Use a dry run instead:**

```bash
gh workflow run "Substack PM Weekly" \
  --repo fayad-abbasi/ai-podcast-generator --ref main \
  -f dry_run=true
```

A dry run exercises **ingest → all per-newsletter summaries → aggregate → action
items → script generation**, which is every model call and every JSON parse path.
It stops before TTS, so it:

- writes no episode and cannot overwrite one
- does not touch `feed.xml`
- does not call `mark_run_complete()`, so the backlog is untouched

Cost is a few minutes and some tokens. Cheaper than finding out at 02:00 Friday.

**The rule, same as for fixes: a merged dependency bump is _deployed_, not _verified_.**

---

## Recovering a backlog

Failures do not consume items — state is only committed on success. But the
**7-day lookback** does age them out, and the **10-item cap** drops the oldest.

After a run of failures:

1. Dispatch once — takes the newest 10 and marks them seen.
2. Dispatch again — takes the next 10, if still inside the lookback.
3. For anything older than 7 days, raise the window:

```bash
gh workflow run "Substack PM Weekly" \
  --repo fayad-abbasi/ai-podcast-generator --ref main \
  -f lookback_days=14
```

⚠️ **Backlog recovery is time-limited.** Every day that passes moves more items
out of any window you widen to. Do it the day you notice.

⚠️ **Do not run two dispatches concurrently** — both will try to commit
`state/substack_seen.json` and the episode, and they will fight.

---

## Known failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `aggregate_summarize failed: last response: ```json` with no `rejected` line | Literal newlines inside a JSON string; `json.loads` rejects control characters by default | `strict=False` (#32) |
| `Invalid summarize_one output ... retrying` on every item | Same as above — systematic parse failure, not content-specific | Same |
| Response looks valid in the error but won't parse | Error truncates at 200 chars and hides the decode reason | Read the failure report, not the exception (#33) |
