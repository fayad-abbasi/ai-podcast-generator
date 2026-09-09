"""The failure report is the thing that was missing in September.

These tests assert it carries the payload that had to be dug out by hand:
the FULL unparseable response and the reason each parse strategy rejected it.
"""

import json

from src import _diagnostics as diagnostics


class TestDiagnostics:
    def setup_method(self):
        diagnostics.reset()

    def test_records_full_response_and_reasons(self):
        diagnostics.record_response(
            "aggregate_summarize",
            '```json\n{"narrative": "a\n\nb"}\n```',
            errors=["raw: Expecting value", "fence: Invalid control character at"],
            item=None,
        )
        report = diagnostics.build_report()
        assert len(report["failed_responses"]) == 1
        r = report["failed_responses"][0]
        assert r["stage"] == "aggregate_summarize"
        assert "Invalid control character" in " ".join(r["errors"])
        assert "narrative" in r["response"]

    def test_response_is_capped_but_flagged(self):
        diagnostics.record_response("s", "x" * (diagnostics.MAX_RESPONSE_CHARS + 500))
        r = diagnostics.build_report()["failed_responses"][0]
        assert r["response_truncated"] is True
        assert r["response_chars"] == diagnostics.MAX_RESPONSE_CHARS + 500
        assert len(r["response"]) == diagnostics.MAX_RESPONSE_CHARS

    def test_caps_number_of_responses(self):
        for i in range(diagnostics.MAX_RESPONSES + 5):
            diagnostics.record_response("s", f"resp {i}")
        assert len(diagnostics.build_report()["failed_responses"]) == diagnostics.MAX_RESPONSES

    def test_report_carries_exception_and_traceback(self):
        try:
            raise ValueError("aggregate_summarize failed")
        except ValueError as e:
            report = diagnostics.build_report(e)
        assert report["exception"]["type"] == "ValueError"
        assert "aggregate_summarize failed" in report["exception"]["message"]
        assert "ValueError" in report["exception"]["traceback"]

    def test_report_carries_model_config(self):
        """A model bump broke this pipeline once; the report must say which model ran."""
        assert "CLAUDE_MODEL" in diagnostics.build_report()["config"]

    def test_render_text_includes_reason_not_just_response(self):
        diagnostics.record_response(
            "aggregate_summarize", '{"narrative": "x"}',
            errors=["braces: Invalid control character at"],
        )
        try:
            raise ValueError("boom")
        except ValueError as e:
            text = diagnostics.render_text(diagnostics.build_report(e))
        assert "Invalid control character" in text
        assert "UNPARSEABLE RESPONSES" in text

    def test_write_report_roundtrips(self, tmp_path):
        diagnostics.note("source", "substack_pm")
        p = diagnostics.write_report(tmp_path / "d" / "failure.json", ValueError("x"))
        assert p.exists()
        data = json.loads(p.read_text())
        assert data["notes"]["source"] == "substack_pm"

    def test_reset_clears_state(self):
        diagnostics.record_response("s", "x")
        diagnostics.note("k", "v")
        diagnostics.reset()
        report = diagnostics.build_report()
        assert report["failed_responses"] == []
        assert report["notes"] == {}
