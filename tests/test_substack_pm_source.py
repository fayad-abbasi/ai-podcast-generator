import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from src.sources.substack_pm import SubstackPMSource


SAMPLE_HTML = (Path(__file__).parent / "fixtures" / "substack_sample.html").read_text()


def _ms(iso_str: str) -> int:
    return int(datetime.fromisoformat(iso_str).timestamp() * 1000)


def _ids(items: list[dict]) -> set[str]:
    return {item["id"] for item in items}


def _gmail_message(
    msg_id: str,
    subject: str,
    from_addr: str,
    html: str = SAMPLE_HTML,
    internal_date: str | int = "1700000000000",
) -> dict:
    return {
        "id": msg_id,
        "internal_date": str(internal_date),
        "headers": {"subject": subject, "from": from_addr},
        "html_body": html,
        "plain_body": "",
    }


@pytest.fixture
def state_path(tmp_path):
    p = tmp_path / "state" / "substack_seen.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"last_run_utc": None, "seen_message_ids": [], "retention_days": 30}))
    return p


class TestFetch:
    @patch("src.sources.substack_pm.fetch_messages")
    def test_returns_content_items(self, mock_fetch, state_path):
        mock_fetch.return_value = [
            _gmail_message("m1", "Build vs Buy Trap", "Lenny <lenny@substack.com>"),
        ]
        items = SubstackPMSource(seen_file_path=state_path).fetch(since_days=7)

        assert len(items) == 1
        item = items[0]
        assert item["id"] == "m1"
        assert item["title"] == "Build vs Buy Trap"
        assert item["url"].startswith("https://")
        assert item["author"] == "Lenny"
        assert isinstance(item["published"], datetime)
        assert len(item["body_text"]) > 500
        assert item["source_meta"]["publication"] == "Lenny"

    @patch("src.sources.substack_pm.fetch_messages")
    def test_dedup_filters_known_ids(self, mock_fetch, state_path):
        state_path.write_text(json.dumps({
            "last_run_utc": None,
            "seen_message_ids": ["already_seen"],
            "retention_days": 30,
        }))
        mock_fetch.return_value = [
            _gmail_message("already_seen", "Old", "x@substack.com"),
            _gmail_message("new_id", "New", "x@substack.com"),
        ]
        items = SubstackPMSource(seen_file_path=state_path).fetch()
        assert _ids(items) == {"new_id"}

    @patch("src.sources.substack_pm.fetch_messages")
    def test_skips_short_bodies(self, mock_fetch, state_path):
        mock_fetch.return_value = [
            _gmail_message("short", "Tiny", "x@substack.com", html="<html><body><p>too short</p></body></html>"),
            _gmail_message("ok", "Real", "x@substack.com"),
        ]
        items = SubstackPMSource(seen_file_path=state_path).fetch()
        assert _ids(items) == {"ok"}

    @patch("src.sources.substack_pm.fetch_messages")
    def test_strips_re_fwd_subject_prefixes(self, mock_fetch, state_path):
        mock_fetch.return_value = [
            _gmail_message("m1", "Re: Fwd: Build vs Buy Trap", "x@substack.com"),
        ]
        items = SubstackPMSource(seen_file_path=state_path).fetch()
        assert items[0]["title"] == "Build vs Buy Trap"

    @patch("src.sources.substack_pm.fetch_messages")
    def test_first_run_uses_since_days_query(self, mock_fetch, state_path):
        mock_fetch.return_value = []
        SubstackPMSource(seen_file_path=state_path).fetch(since_days=14)
        query = mock_fetch.call_args.args[0]
        assert "label:Substack/PM" in query
        assert "newer_than:14d" in query

    @patch("src.sources.substack_pm.fetch_messages")
    def test_after_first_run_uses_last_run_query(self, mock_fetch, state_path):
        state_path.write_text(json.dumps({
            "last_run_utc": "2026-05-22T09:49:35+00:00",
            "seen_message_ids": [],
            "retention_days": 30,
        }))
        mock_fetch.return_value = []

        SubstackPMSource(seen_file_path=state_path).fetch(since_days=14)

        query = mock_fetch.call_args.args[0]
        assert "label:Substack/PM" in query
        assert "after:2026/05/21" in query
        assert "newer_than:" not in query

    @patch("src.sources.substack_pm.fetch_messages")
    def test_filters_messages_before_last_run_precisely(self, mock_fetch, state_path):
        cutoff_iso = "2026-05-22T09:49:35+00:00"
        cutoff_ms = _ms(cutoff_iso)
        state_path.write_text(json.dumps({
            "last_run_utc": cutoff_iso,
            "seen_message_ids": [],
            "retention_days": 30,
        }))
        mock_fetch.return_value = [
            _gmail_message("old", "Old", "x@substack.com", internal_date=cutoff_ms - 1),
            _gmail_message("new", "New", "x@substack.com", internal_date=cutoff_ms + 1),
        ]

        items = SubstackPMSource(seen_file_path=state_path).fetch()

        assert _ids(items) == {"new"}

    @patch("src.sources.substack_pm.SUBSTACK_MAX_NEWSLETTERS_PER_RUN", 3)
    @patch("src.sources.substack_pm.fetch_messages")
    def test_caps_at_max_keeps_newest(self, mock_fetch, state_path):
        # 5 messages with monotonically increasing internal_date (newest last)
        mock_fetch.return_value = [
            _gmail_message(f"m{i}", f"Title {i}", "x@substack.com", internal_date=1700000000000 + i * 86400000)
            for i in range(5)
        ]
        items = SubstackPMSource(seen_file_path=state_path).fetch()

        assert len(items) == 3
        assert _ids(items) == {"m2", "m3", "m4"}

    @patch("src.sources.substack_pm.fetch_messages")
    def test_second_run_only_returns_messages_after_completed_first_run(self, mock_fetch, state_path):
        first_run_iso = "2026-05-22T09:49:35+00:00"
        first_run_ms = _ms(first_run_iso)
        second_run_ms = first_run_ms + 60_000
        mock_fetch.return_value = [
            _gmail_message("first", "First", "x@substack.com", internal_date=first_run_ms),
        ]
        src = SubstackPMSource(seen_file_path=state_path)

        first_items = src.fetch()
        assert _ids(first_items) == {"first"}

        state_path.write_text(json.dumps({
            "last_run_utc": first_run_iso,
            "seen_message_ids": ["first"],
            "retention_days": 30,
        }))
        mock_fetch.return_value = [
            _gmail_message("before_cutoff", "Before", "x@substack.com", internal_date=first_run_ms - 1),
            _gmail_message("at_cutoff", "At", "x@substack.com", internal_date=first_run_ms),
            _gmail_message("after_cutoff", "After", "x@substack.com", internal_date=second_run_ms),
        ]
        second_items = SubstackPMSource(seen_file_path=state_path).fetch()

        assert _ids(second_items) == {"after_cutoff"}

    @patch("src.sources.substack_pm.fetch_messages")
    def test_clean_empty_run_prevents_old_messages_from_reappearing(self, mock_fetch, state_path):
        state_path.write_text(json.dumps({
            "last_run_utc": "2026-05-22T09:49:35+00:00",
            "seen_message_ids": [],
            "retention_days": 30,
        }))
        src = SubstackPMSource(seen_file_path=state_path)
        src.mark_run_complete()
        completed_at = datetime.fromisoformat(json.loads(state_path.read_text())["last_run_utc"])

        mock_fetch.return_value = [
            _gmail_message(
                "older_unseen",
                "Older Unseen",
                "x@substack.com",
                internal_date=int((completed_at.timestamp() * 1000) - 1),
            ),
        ]

        items = SubstackPMSource(seen_file_path=state_path).fetch()

        assert items == []


class TestMarkProcessed:
    @patch("src.sources.substack_pm.fetch_messages")
    def test_persists_pending_ids(self, mock_fetch, state_path):
        mock_fetch.return_value = [
            _gmail_message("a", "A", "x@substack.com"),
            _gmail_message("b", "B", "x@substack.com"),
        ]
        src = SubstackPMSource(seen_file_path=state_path)
        src.fetch()
        src.mark_processed()

        state = json.loads(state_path.read_text())
        assert set(state["seen_message_ids"]) == {"a", "b"}
        assert state["last_run_utc"] is not None

    @patch("src.sources.substack_pm.fetch_messages")
    def test_explicit_ids_override_pending(self, mock_fetch, state_path):
        mock_fetch.return_value = [_gmail_message("a", "A", "x@substack.com")]
        src = SubstackPMSource(seen_file_path=state_path)
        src.fetch()
        src.mark_processed(["custom_id"])
        state = json.loads(state_path.read_text())
        assert state["seen_message_ids"] == ["custom_id"]

    def test_noop_when_no_pending(self, state_path):
        before = state_path.read_text()
        SubstackPMSource(seen_file_path=state_path).mark_processed()
        assert state_path.read_text() == before

    def test_mark_run_complete_updates_last_run_without_ids(self, state_path):
        SubstackPMSource(seen_file_path=state_path).mark_run_complete()

        state = json.loads(state_path.read_text())
        assert state["seen_message_ids"] == []
        assert state["last_run_utc"] is not None
        assert datetime.fromisoformat(state["last_run_utc"]).tzinfo == timezone.utc

    @patch("src.sources.substack_pm.fetch_messages")
    def test_appends_to_existing_seen(self, mock_fetch, state_path):
        state_path.write_text(json.dumps({
            "last_run_utc": "2026-04-01T00:00:00+00:00",
            "seen_message_ids": ["old1", "old2"],
            "retention_days": 30,
        }))
        mock_fetch.return_value = [
            _gmail_message(
                "new1",
                "X",
                "x@substack.com",
                internal_date=str(_ms("2026-04-02T00:00:00+00:00")),
            ),
        ]
        src = SubstackPMSource(seen_file_path=state_path)
        src.fetch()
        src.mark_processed()
        state = json.loads(state_path.read_text())
        assert set(state["seen_message_ids"]) == {"old1", "old2", "new1"}
