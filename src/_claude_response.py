"""Helpers for reading Anthropic Messages API responses.

`response.content` is a list of content blocks whose composition depends on the
request. With thinking enabled the first block is a `thinking` block, not the
text — and on models where thinking `display` defaults to "omitted" that block
carries an empty string. Indexing `content[0].text` therefore fails silently:
the call succeeds, the pipeline publishes, and the episode is empty.

Selecting the block by type instead of by position is correct under every
thinking setting, so the model and thinking config can change without
re-breaking every call site.
"""


def _block_type(block) -> str | None:
    """The block's `type`, or None if it doesn't carry a real one.

    Test doubles built from `MagicMock` auto-generate every attribute, so
    `block.type` is a Mock rather than a string. Requiring `str` keeps those
    doubles on the positional fallback instead of misreading them as typed.
    """
    kind = getattr(block, "type", None)
    return kind if isinstance(kind, str) else None


def first_text_block(response) -> str:
    """Return the text of the first `text` block in an API response."""
    blocks = getattr(response, "content", None) or []

    for block in blocks:
        if _block_type(block) == "text":
            return block.text

    kinds = sorted({k for k in (_block_type(b) for b in blocks) if k})
    if kinds:
        raise ValueError(
            f"No text block in Claude response (found: {', '.join(kinds)}). "
            "If thinking is enabled, the text block is not content[0]."
        )

    if blocks:
        return blocks[0].text

    raise ValueError("Claude response contained no content blocks")
