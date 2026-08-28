"""Tests for reading text out of Anthropic Messages API responses.

These exist because the pipeline previously read `response.content[0].text`.
That is correct only when thinking is off. On models where thinking is on by
default the first block is a thinking block, and where `display` defaults to
"omitted" it carries an empty string — so the old code returned "" and the
pipeline published empty episodes without raising.
"""

from types import SimpleNamespace

import pytest

from src._claude_response import first_text_block


def block(kind, text):
    return SimpleNamespace(type=kind, text=text)


class TestFirstTextBlock:
    def test_returns_text_when_text_block_is_first(self):
        response = SimpleNamespace(content=[block("text", "the script")])
        assert first_text_block(response) == "the script"

    def test_skips_leading_thinking_block(self):
        """The regression this helper exists for."""
        response = SimpleNamespace(
            content=[block("thinking", ""), block("text", "the script")]
        )
        assert first_text_block(response) == "the script"

    def test_skips_thinking_block_carrying_summarized_reasoning(self):
        response = SimpleNamespace(
            content=[block("thinking", "Let me consider..."), block("text", "answer")]
        )
        assert first_text_block(response) == "answer"

    def test_returns_first_text_block_when_several_present(self):
        response = SimpleNamespace(
            content=[block("thinking", ""), block("text", "one"), block("text", "two")]
        )
        assert first_text_block(response) == "one"

    def test_raises_when_only_non_text_blocks(self):
        """Better a loud failure than an empty episode."""
        response = SimpleNamespace(content=[block("thinking", "")])
        with pytest.raises(ValueError, match="No text block"):
            first_text_block(response)

    def test_error_names_the_block_types_found(self):
        response = SimpleNamespace(
            content=[block("thinking", ""), block("tool_use", "")]
        )
        with pytest.raises(ValueError, match="thinking, tool_use"):
            first_text_block(response)

    def test_raises_on_empty_content(self):
        response = SimpleNamespace(content=[])
        with pytest.raises(ValueError, match="no content blocks"):
            first_text_block(response)

    def test_raises_when_content_attribute_missing(self):
        with pytest.raises(ValueError, match="no content blocks"):
            first_text_block(SimpleNamespace())

    def test_falls_back_to_position_for_untyped_mocks(self):
        """Existing suites build responses from bare MagicMocks with no `type`."""
        from unittest.mock import MagicMock

        mock_block = MagicMock()
        mock_block.type = None
        mock_block.text = "from a mock"
        response = SimpleNamespace(content=[mock_block])
        assert first_text_block(response) == "from a mock"
