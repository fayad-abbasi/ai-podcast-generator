"""Breadcrumbs that let a failed run explain itself.

The 2026-09-02/04/09 Substack PM Weekly failures cost three debugging rounds
and one wrong diagnosis, because the only thing that ever surfaced was
`raw[:200]`: *what* the model returned, never *why* it was rejected. Worse,
those 200 characters looked like well-formed JSON, which pointed the first fix
at the validator — a layer the pipeline had never actually reached.

Anything recorded here is written into a failure report when the pipeline
raises. The captured responses double as regression fixtures: drop one into
tests/fixtures/ and the bug hands you its own test.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

# A failing response is worth reading in full; a runaway one is not.
MAX_RESPONSE_CHARS = 8000
MAX_RESPONSES = 12

_responses: list[dict] = []
_notes: dict = {}


def reset() -> None:
    """Clear state. Mainly for tests."""
    _responses.clear()
    _notes.clear()


def note(key: str, value) -> None:
    """Record a scalar fact about this run — stage, model, item counts."""
    _notes[key] = value


def record_response(
    stage: str,
    raw: str,
    errors: list[str] | None = None,
    item: str | None = None,
) -> None:
    """Capture a model response that could not be parsed.

    `errors` is the reason *each* parse strategy rejected it. That is the
    field whose absence caused the September misdiagnosis.
    """
    if len(_responses) >= MAX_RESPONSES:
        return
    raw = raw or ""
    _responses.append({
        "stage": stage,
        "item": item,
        "errors": list(errors or []),
        "response_chars": len(raw),
        "response_truncated": len(raw) > MAX_RESPONSE_CHARS,
        "response": raw[:MAX_RESPONSE_CHARS],
    })


def _github_context() -> dict:
    keys = (
        "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA",
        "GITHUB_REF_NAME", "GITHUB_WORKFLOW", "GITHUB_EVENT_NAME",
        "GITHUB_REPOSITORY", "GITHUB_SERVER_URL",
    )
    ctx = {k: os.environ[k] for k in keys if os.environ.get(k)}
    if ctx.get("GITHUB_RUN_ID") and ctx.get("GITHUB_REPOSITORY"):
        server = ctx.get("GITHUB_SERVER_URL", "https://github.com")
        ctx["run_url"] = (
            f"{server}/{ctx['GITHUB_REPOSITORY']}/actions/runs/{ctx['GITHUB_RUN_ID']}"
        )
    return ctx


def _model_context() -> dict:
    """Config that shapes model output. A model bump broke this pipeline once."""
    try:
        from src import config
    except Exception:
        return {}
    return {
        k: getattr(config, k)
        for k in (
            "CLAUDE_MODEL", "CLAUDE_THINKING", "SUMMARIZE_MAX_TOKENS",
            "SUBSTACK_LOOKBACK_DAYS", "SUBSTACK_MAX_NEWSLETTERS_PER_RUN",
        )
        if hasattr(config, k)
    }


def build_report(exc: BaseException | None = None) -> dict:
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "github": _github_context(),
        "config": _model_context(),
        "notes": dict(_notes),
        "failed_responses": list(_responses),
    }
    if exc is not None:
        report["exception"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ),
        }
    return report


def render_text(report: dict) -> str:
    """Plain-text rendering — this is what lands in the failure email."""
    lines: list[str] = []
    exc = report.get("exception") or {}
    gh = report.get("github") or {}

    lines.append(f"{exc.get('type', 'Failure')}: {exc.get('message', '(no message)')}")
    lines.append("")
    if gh.get("run_url"):
        lines.append(f"Run:    {gh['run_url']}")
    if gh.get("GITHUB_SHA"):
        lines.append(f"Commit: {gh['GITHUB_SHA'][:12]} on {gh.get('GITHUB_REF_NAME', '?')}")
    lines.append(f"When:   {report.get('generated_at')}")
    lines.append("")

    if report.get("config"):
        lines.append("CONFIG")
        for k, v in report["config"].items():
            lines.append(f"  {k} = {v}")
        lines.append("")

    if report.get("notes"):
        lines.append("RUN NOTES")
        for k, v in report["notes"].items():
            lines.append(f"  {k} = {v}")
        lines.append("")

    responses = report.get("failed_responses") or []
    if responses:
        lines.append(f"UNPARSEABLE RESPONSES ({len(responses)})")
        for i, r in enumerate(responses, 1):
            lines.append(f"  [{i}] stage={r['stage']} item={r.get('item') or '-'}")
            for err in r.get("errors", []):
                lines.append(f"      reject: {err}")
            lines.append(
                f"      {r['response_chars']} chars"
                + (" (truncated below)" if r.get("response_truncated") else "")
            )
            lines.append("      ---- response ----")
            for ln in (r.get("response") or "").splitlines():
                lines.append(f"      {ln}")
            lines.append("      ------------------")
        lines.append("")

    if exc.get("traceback"):
        lines.append("TRACEBACK")
        lines.append(exc["traceback"])

    return "\n".join(lines)


def write_report(path: str | Path, exc: BaseException | None = None) -> Path:
    """Write the JSON report. Returns the path written."""
    report = build_report(exc)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return p
