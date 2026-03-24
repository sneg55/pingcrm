"""Tests for Twitter handle extraction from Telegram bios."""
import pytest

from app.integrations.telegram_helpers import _extract_twitter_handle


class TestExtractTwitterHandle:
    def test_twitter_url(self):
        assert _extract_twitter_handle("Follow me https://twitter.com/johndoe") == "johndoe"

    def test_x_url(self):
        assert _extract_twitter_handle("DMs open x.com/janedoe") == "janedoe"

    def test_x_url_with_https(self):
        assert _extract_twitter_handle("https://x.com/alice_bob") == "alice_bob"

    def test_twitter_url_with_at(self):
        assert _extract_twitter_handle("twitter.com/@myhandle") == "myhandle"

    def test_mention_near_twitter_keyword(self):
        assert _extract_twitter_handle("twitter: @johndoe") == "johndoe"

    def test_mention_near_x_keyword(self):
        assert _extract_twitter_handle("𝕏 @cryptobro") == "cryptobro"

    def test_mention_near_tw_keyword(self):
        assert _extract_twitter_handle("tw: @devguy") == "devguy"

    def test_no_handle_in_plain_text(self):
        assert _extract_twitter_handle("I love programming") is None

    def test_no_handle_with_at_but_no_keyword(self):
        assert _extract_twitter_handle("Contact @someone for details") is None

    def test_filters_twitter_reserved_paths(self):
        assert _extract_twitter_handle("https://twitter.com/home") is None
        assert _extract_twitter_handle("https://twitter.com/search") is None
        assert _extract_twitter_handle("https://twitter.com/settings") is None
        assert _extract_twitter_handle("https://twitter.com/explore") is None

    def test_filters_common_non_twitter_mentions(self):
        bio = "twitter: @telegram for updates"
        assert _extract_twitter_handle(bio) is None

    def test_empty_string(self):
        assert _extract_twitter_handle("") is None

    def test_x_com_in_bio_with_mention(self):
        assert _extract_twitter_handle("Find me on x.com @realhandle") == "realhandle"

    def test_www_twitter_url(self):
        assert _extract_twitter_handle("www.twitter.com/myuser") == "myuser"
