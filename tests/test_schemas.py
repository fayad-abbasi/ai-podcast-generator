"""The output_config schema subset is narrower than JSON Schema.

Run 35452947732 (2026-09-19) died with a 400 before the model was ever called:
`minItems` accepts only 0 or 1, and `maxItems`, `minimum` and `maximum` are not
supported at all. The count and the 10-30 bound are enforced in
_rejection() instead; these tests keep them from creeping back into the schema.
"""

import pytest

from src.config import ACTION_ITEMS_COUNT
from src.schemas import NEWSLETTER_SUMMARY_SCHEMA, action_items_schema

UNSUPPORTED = ("maxItems", "minimum", "maximum", "multipleOf",
               "minLength", "maxLength", "pattern")


def walk(node, path="root"):
    """Yield (path, schema-dict) for every schema object in the tree."""
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            yield from walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from walk(value, f"{path}[{i}]")


@pytest.mark.parametrize("name,schema", [
    ("newsletter", NEWSLETTER_SUMMARY_SCHEMA),
    ("action_items", action_items_schema(ACTION_ITEMS_COUNT)),
])
class TestOnlySupportedKeywords:
    def test_uses_no_unsupported_keyword(self, name, schema):
        found = [
            f"{path}.{key}"
            for path, node in walk(schema)
            for key in UNSUPPORTED
            if key in node
        ]
        assert found == [], f"{name} schema uses unsupported keywords: {found}"

    def test_min_items_is_zero_or_one(self, name, schema):
        values = [node["minItems"] for _, node in walk(schema) if "minItems" in node]
        assert all(v in (0, 1) for v in values), f"{name} schema has minItems {values}"

    def test_objects_forbid_additional_properties(self, name, schema):
        for path, node in walk(schema):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False, f"{name}: {path}"
