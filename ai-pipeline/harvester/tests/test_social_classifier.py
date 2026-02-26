"""Tests for search/social_classifier.py."""

from search.social_classifier import (
    SocialLink,
    SocialPlatform,
    classify_social_url,
    extract_social_links,
)


class TestClassifySocialUrl:
    # --- VK ---
    def test_vk_club(self):
        link = classify_social_url("https://vk.com/club12345")
        assert link.platform == SocialPlatform.VK
        assert link.numeric_id == 12345
        assert link.slug == "club12345"
        assert link.source_kind == "vk_group"

    def test_vk_public(self):
        link = classify_social_url("https://vk.com/public99999")
        assert link.platform == SocialPlatform.VK
        assert link.numeric_id == 99999

    def test_vk_slug(self):
        link = classify_social_url("https://vk.com/kcson_vologda")
        assert link.platform == SocialPlatform.VK
        assert link.slug == "kcson_vologda"
        assert link.numeric_id is None

    def test_vk_ignores_share(self):
        link = classify_social_url("https://vk.com/share?url=foo")
        assert link.platform == SocialPlatform.NONE

    def test_vk_trailing_slash(self):
        link = classify_social_url("https://vk.com/kcson_anapa/")
        assert link.platform == SocialPlatform.VK
        assert link.slug == "kcson_anapa"

    # --- OK ---
    def test_ok_group(self):
        link = classify_social_url("https://ok.ru/group/54321")
        assert link.platform == SocialPlatform.OK
        assert link.numeric_id == 54321
        assert link.source_kind == "ok_group"

    def test_ok_profile(self):
        link = classify_social_url("https://ok.ru/profile/111")
        assert link.platform == SocialPlatform.OK
        assert link.numeric_id == 111

    def test_ok_slug(self):
        link = classify_social_url("https://ok.ru/kcsonvologda")
        assert link.platform == SocialPlatform.OK
        assert link.slug == "kcsonvologda"

    # --- Telegram ---
    def test_tg_channel(self):
        link = classify_social_url("https://t.me/kcson_news")
        assert link.platform == SocialPlatform.TELEGRAM
        assert link.slug == "kcson_news"
        assert link.source_kind == "tg_channel"

    def test_tg_ignores_joinchat(self):
        link = classify_social_url("https://t.me/joinchat")
        assert link.platform == SocialPlatform.NONE

    # --- Not social ---
    def test_regular_url(self):
        link = classify_social_url("https://kcson-vologda.gov35.ru")
        assert link.platform == SocialPlatform.NONE
        assert not link.is_social

    def test_empty_url(self):
        link = classify_social_url("")
        assert link.platform == SocialPlatform.NONE


class TestExtractSocialLinks:
    def test_mixed(self):
        urls = [
            "https://kcson.ru",
            "https://vk.com/club123",
            "https://ok.ru/group/456",
            "https://example.com",
            "https://t.me/channel1",
        ]
        social = extract_social_links(urls)
        assert len(social) == 3
        platforms = {s.platform for s in social}
        assert platforms == {SocialPlatform.VK, SocialPlatform.OK, SocialPlatform.TELEGRAM}

    def test_no_social(self):
        urls = ["https://kcson.ru", "https://fond.ru"]
        assert extract_social_links(urls) == []
