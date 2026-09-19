from pathlib import Path
from urllib.parse import urlparse

import pytest

from src.sources._substack_body import (
    BodyTooShort,
    extract_post,
    _find_canonical_url,
    _strip_chrome_lines,
)
from bs4 import BeautifulSoup


FIXTURE = Path(__file__).parent / "fixtures" / "substack_sample.html"


class TestExtractPost:
    def test_returns_canonical_url_and_text(self):
        html = FIXTURE.read_text()
        url, text = extract_post(html)
        assert url == "https://lennysnewsletter.substack.com/p/build-vs-buy-trap"
        assert len(text) > 500
        assert "Build vs. Buy" in text or "build-vs-buy" in text.lower() or "build" in text.lower()

    def test_strips_unsubscribe_lines(self):
        html = FIXTURE.read_text()
        _, text = extract_post(html)
        assert "Unsubscribe" not in text
        assert "Manage your subscription" not in text

    def test_raises_on_short_body(self):
        with pytest.raises(BodyTooShort):
            extract_post("<html><body><p>too short</p></body></html>")

    def test_raises_on_empty_html(self):
        with pytest.raises(BodyTooShort):
            extract_post("")


class TestFindCanonicalUrl:
    def test_prefers_link_canonical(self):
        html = '<html><head><link rel="canonical" href="https://example.com/post"/></head></html>'
        soup = BeautifulSoup(html, "lxml")
        assert _find_canonical_url(soup, html) == "https://example.com/post"

    def test_falls_back_to_og_url(self):
        html = '<html><head><meta property="og:url" content="https://example.com/og"/></head></html>'
        soup = BeautifulSoup(html, "lxml")
        assert _find_canonical_url(soup, html) == "https://example.com/og"

    def test_falls_back_to_substack_pattern(self):
        html = '<html><body><a href="https://lenny.substack.com/p/some-slug">x</a></body></html>'
        soup = BeautifulSoup(html, "lxml")
        url = _find_canonical_url(soup, html)
        assert url == "https://lenny.substack.com/p/some-slug"

    def test_falls_back_to_any_substack_domain_url(self):
        """No /p/ pattern, but a substack.com domain URL is present."""
        html = '<html><body><a href="https://producttalk.substack.com/post/123-something">read</a></body></html>'
        soup = BeautifulSoup(html, "lxml")
        url = _find_canonical_url(soup, html)
        host = urlparse(url).hostname
        assert host is not None
        assert host == "substack.com" or host.endswith(".substack.com")

    def test_skips_chrome_substack_links(self):
        """Account/profile/redirect Substack URLs aren't valid post canonicals."""
        html = (
            '<html><body>'
            '<a href="https://example.substack.com/account">Manage</a>'
            '</body></html>'
        )
        soup = BeautifulSoup(html, "lxml")
        # Should not return the /account URL
        url = _find_canonical_url(soup, html)
        assert "/account" not in url or url == ""

    def test_returns_empty_when_none_found(self):
        html = "<html><body>nothing here</body></html>"
        soup = BeautifulSoup(html, "lxml")
        assert _find_canonical_url(soup, html) == ""


class TestStripChromeLines:
    def test_removes_unsubscribe(self):
        text = "Real content line\nUnsubscribe from this list\nMore content"
        cleaned = _strip_chrome_lines(text)
        assert "Real content line" in cleaned
        assert "More content" in cleaned
        assert "Unsubscribe" not in cleaned

    def test_drops_empty_lines(self):
        assert _strip_chrome_lines("a\n\n\nb") == "a\nb"


# ── newsletters that are not on substack.com ───────────────────


GHOST_EMAIL = """
<html><body>
  <a href="https://www.examplepub.org/r/09af81ff?m=SUBSCRIBER-UUID">Product Talk</a>
  <a href="https://www.examplepub.org/r/937de553?m=SUBSCRIBER-UUID">Creating Aha! Builder</a>
  <a href="https://www.examplepub.org/r/64caadaf?m=SUBSCRIBER-UUID">View in browser</a>
  <a href="https://www.examplepub.org/members/feedback/abc/1/?uuid=SUBSCRIBER-UUID">More like this</a>
  <a href="https://www.examplepub.org/#/portal/account">Manage subscription</a>
  <a href="https://www.examplepub.org/unsubscribe/?uuid=SUBSCRIBER-UUID&key=SECRET">Unsubscribe</a>
  <p>%s</p>
</body></html>
""" % ("Body text " * 100)


class TestNonSubstackNewsletters:
    """Half the emails under the Substack/PM label are not Substack at all.

    Product Talk is a Ghost newsletter: every link is a tracking redirect
    (/r/<hash>?m=<subscriber-uuid>) and no plain post URL appears anywhere.
    _find_canonical_url returned "" for all of them, which is what put
    `source_url: ""` in front of the action-items validator on 2026-09-18.
    """

    def test_uses_the_view_in_browser_link_when_nothing_else_is_available(self):
        soup = BeautifulSoup(GHOST_EMAIL, "lxml")

        url = _find_canonical_url(soup, GHOST_EMAIL)

        assert url.startswith("https://www.examplepub.org/r/64caadaf")

    def test_strips_the_subscriber_token_from_the_url(self):
        """These URLs end up in a public repo. The ?m= token identifies Fayad."""
        soup = BeautifulSoup(GHOST_EMAIL, "lxml")

        url = _find_canonical_url(soup, GHOST_EMAIL)

        assert url == "https://www.examplepub.org/r/64caadaf"

    def test_returns_nothing_rather_than_guess_when_there_is_no_view_in_browser(self):
        """Better an empty url than a citation pointing at an unsubscribe page."""
        html = GHOST_EMAIL.replace(
            '<a href="https://www.examplepub.org/r/64caadaf?m=SUBSCRIBER-UUID">View in browser</a>', ""
        )
        soup = BeautifulSoup(html, "lxml")

        assert _find_canonical_url(soup, html) == ""

    def test_a_substack_url_still_wins_over_a_view_in_browser_link(self):
        html = GHOST_EMAIL.replace(
            "<p>", '<a href="https://lenny.substack.com/p/real-post">Read</a><p>', 1
        )
        soup = BeautifulSoup(html, "lxml")

        assert _find_canonical_url(soup, html) == "https://lenny.substack.com/p/real-post"
