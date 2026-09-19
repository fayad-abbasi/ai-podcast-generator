import json
import logging
import time
from pathlib import Path
from typing import TypedDict

import anthropic

from src.config import (
    ACTION_ITEMS_COUNT,
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    CLAUDE_THINKING,
    PROMPTS_DIR,
    ROOT_DIR,
    SUMMARIZE_MAX_TOKENS,
    SUMMARIZE_TEMPERATURE,
)
from src import _diagnostics as diagnostics
from src._claude_response import first_text_block
from src.schemas import action_items_schema
from src.summarize import AggregateSummary, NewsletterSummary, _try_parse_json

logger = logging.getLogger(__name__)

API_RETRY_DELAYS = [2, 8, 32]
RETRYABLE_STATUS_CODES = (429, 500, 503)

CONTEXT_DIR = ROOT_DIR / "prompts" / "context"
ROLE_FILE = CONTEXT_DIR / "role.md"
PROJECTS_FILE = CONTEXT_DIR / "projects.md"


class ActionItem(TypedDict):
    title: str
    description: str
    source_url: str
    estimated_minutes: int


def load_memory_slices(
    role_path: Path | None = None,
    projects_path: Path | None = None,
) -> dict[str, str]:
    """Read role.md and projects.md verbatim.

    A missing file raises. A file with headings but no content warns loudly and
    continues: it degrades the items to generic PM advice but does not stop the
    week's episode from publishing.
    """
    role_file = role_path or ROLE_FILE
    projects_file = projects_path or PROJECTS_FILE
    role = role_file.read_text()
    projects = projects_file.read_text()
    for path, text in ((role_file, role), (projects_file, projects)):
        if not _has_content(text):
            logger.warning(
                "%s has headings but no content. action_items.txt asks the model to "
                "be specific about Fayad and this is where that specificity comes "
                "from, so the items will be generic. Not fatal: the run continues.",
                path,
            )
    return {"role": role, "projects": projects}


def _has_content(text: str) -> bool:
    """True when the file has at least one non-heading, non-blank line."""
    return any(
        line.strip() and not line.lstrip().startswith("#")
        for line in text.splitlines()
    )


def generate_action_items(
    per_item: list[NewsletterSummary],
    aggregate: AggregateSummary,
    memory_slices: dict[str, str],
    week_ending: str | None = None,
    prompt_file: str = "action_items.txt",
) -> list[ActionItem]:
    """Generate exactly ACTION_ITEMS_COUNT action items grounded in Fayad's
    role + projects. Validates each item's source_url is present in the
    input newsletter set. Retry-once on validation failure with stricter
    system prompt prefix."""
    template = (PROMPTS_DIR / prompt_file).read_text()
    system_prompt = template.replace(
        "{{role_slice}}", memory_slices.get("role", "")
    ).replace(
        "{{projects_slice}}", memory_slices.get("projects", "")
    )

    user_message = json.dumps({
        "week_ending": week_ending or "",
        "newsletter_summaries": per_item,
        "aggregate": aggregate,
    }, ensure_ascii=False)

    valid_urls = {s.get("url", "") for s in per_item if s.get("url")}

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages = [{"role": "user", "content": user_message}]

    schema = action_items_schema(ACTION_ITEMS_COUNT)
    raw = _call_claude(client, system_prompt, messages, output_schema=schema)
    items = _parse_and_validate(raw, valid_urls)
    if items is not None:
        return items

    logger.warning("action_items validation failed — retrying with stricter prefix")
    stricter_system = (
        "RETURN ONLY VALID JSON. EXACTLY 3 ITEMS. EACH source_url MUST APPEAR "
        "IN THE PROVIDED NEWSLETTERS. estimated_minutes BETWEEN 10 AND 30.\n\n"
    ) + system_prompt
    messages.append({"role": "assistant", "content": raw})
    messages.append({"role": "user", "content": "Your previous response failed validation. Try again."})
    raw = _call_claude(client, stricter_system, messages, output_schema=schema)
    items = _parse_and_validate(raw, valid_urls)
    if items is not None:
        return items

    raise ValueError(f"action_items failed validation after retry: {raw[:200]}")


def _parse_and_validate(raw: str, valid_urls: set[str]) -> list[ActionItem] | None:
    """Return the items, or None — recording why the response was rejected.

    A rejection that leaves no trace is what made run 35336079576 unreadable:
    the first attempt failed and the failure report showed only the retry.
    """
    reason = _rejection(raw, valid_urls)
    if reason is None:
        return _try_parse_json(raw)["items"]
    logger.warning("action_items rejected: %s", reason)
    diagnostics.record_response("action_items", raw, errors=[reason])
    return None


def _rejection(raw: str, valid_urls: set[str]) -> str | None:
    """The reason this response is unusable, or None when it is usable."""
    parsed = _try_parse_json(raw)
    if not parsed or not isinstance(parsed, dict):
        return "response was not a JSON object"
    items = parsed.get("items")
    if not isinstance(items, list):
        return f"'items' was {type(items).__name__}, not a list"
    if len(items) != ACTION_ITEMS_COUNT:
        return f"expected {ACTION_ITEMS_COUNT} items, got {len(items)}"
    for position, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            return f"item {position} was {type(item).__name__}, not an object"
        missing = [
            key for key in ("title", "description", "source_url", "estimated_minutes")
            if key not in item
        ]
        if missing:
            return f"item {position} missing keys: {missing}"
        for key in ("title", "description"):
            if not isinstance(item[key], str) or not item[key].strip():
                return f"item {position} has an empty {key}"
        if not isinstance(item["source_url"], str) or item["source_url"] not in valid_urls:
            return (
                f"item {position} source_url {item['source_url']!r} is not one of this "
                f"week's {len(valid_urls)} newsletter URLs"
            )
        mins = item.get("estimated_minutes")
        if not isinstance(mins, int) or not (10 <= mins <= 30):
            return f"item {position} estimated_minutes {mins!r} is outside 10-30"
    return None


def _call_claude(
    client: anthropic.Anthropic,
    system_prompt: str,
    messages: list[dict],
    output_schema: dict | None = None,
) -> str:
    extra = (
        {"output_config": {"format": {"type": "json_schema", "schema": output_schema}}}
        if output_schema
        else {}
    )
    for attempt, delay in enumerate(API_RETRY_DELAYS):
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=SUMMARIZE_MAX_TOKENS,
                thinking=CLAUDE_THINKING,
#                temperature=SUMMARIZE_TEMPERATURE,  # removed: not accepted by anthropic>=1.1.0
                system=system_prompt,
                messages=messages,
                **extra,
            )
            return first_text_block(response)
        except anthropic.APIStatusError as e:
            if e.status_code in RETRYABLE_STATUS_CODES and attempt < len(API_RETRY_DELAYS) - 1:
                logger.warning(
                    "Claude API error %d (attempt %d/%d), retrying in %ds",
                    e.status_code, attempt + 1, len(API_RETRY_DELAYS), delay,
                )
                time.sleep(delay)
            else:
                raise

    raise RuntimeError("All Claude API retries exhausted")
