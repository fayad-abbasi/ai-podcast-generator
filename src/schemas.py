"""JSON schemas passed to the Messages API as `output_config.format`.

These constrain the response rather than requesting it. The prompts still
describe the shape for the model's benefit, but correctness no longer depends
on the model choosing to comply: the API will not emit a response that fails
these schemas, so `_try_parse_json`'s fallbacks become a backstop instead of
the mechanism.

This closes two failure modes seen on 2026-09-18 (run 35336079576):
  - action_items returned prose ("Given the missing role/project specifics,
    I'll ground each item") instead of JSON, twice, and the run died.
  - three summarize responses carried unescaped double quotes inside string
    values (`internal "meta applications"`), which `strict=False` cannot
    repair -- it permits control characters, not stray quotes.
"""

# Matches NewsletterSummary in src/summarize.py.
NEWSLETTER_SUMMARY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "publication": {"type": "string"},
        "author": {"type": ["string", "null"]},
        "url": {"type": "string"},
        "one_liner": {"type": "string"},
        "summary": {"type": "string"},
        "key_takeaways": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "title",
        "publication",
        "author",
        "url",
        "one_liner",
        "summary",
        "key_takeaways",
    ],
    "additionalProperties": False,
}


def action_items_schema(count: int) -> dict:
    """Schema for the action-items wrapper object.

    `count` is pinned to ACTION_ITEMS_COUNT so the "EXACTLY 3 ITEMS"
    instruction in the prompt becomes an API-enforced constraint rather than
    a request the validator checks after the fact.
    """
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "minItems": count,
                "maxItems": count,
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "source_url": {"type": "string"},
                        "estimated_minutes": {
                            "type": "integer",
                            "minimum": 10,
                            "maximum": 30,
                        },
                    },
                    "required": [
                        "title",
                        "description",
                        "source_url",
                        "estimated_minutes",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }
