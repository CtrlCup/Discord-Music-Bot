import unittest
from utils.track_resolver import _is_deezer_shortlink, SPOTIFY_RE, DEEZER_RE


class TestDeezerShortlinkSSRFGuard(unittest.TestCase):
    """Verhindert, dass !play mit einem beliebigen String, der zufällig 'deezer.page.link'
    enthält, den Bot dazu bringt, eine vom Angreifer gewählte URL abzurufen (SSRF)."""

    def test_genuine_shortlink_is_accepted(self):
        self.assertTrue(_is_deezer_shortlink("https://deezer.page.link/abc123"))
        self.assertTrue(_is_deezer_shortlink("http://deezer.page.link/abc123"))

    def test_ssrf_attempt_via_query_string_is_rejected(self):
        self.assertFalse(_is_deezer_shortlink("http://169.254.169.254/latest/meta-data/?x=deezer.page.link"))

    def test_ssrf_attempt_via_lookalike_host_is_rejected(self):
        self.assertFalse(_is_deezer_shortlink("https://evil.com/deezer.page.link"))
        self.assertFalse(_is_deezer_shortlink("https://deezer.page.link.evil.com/x"))

    def test_missing_scheme_is_rejected(self):
        self.assertFalse(_is_deezer_shortlink("deezer.page.link/abc123"))

    def test_plain_search_text_is_rejected(self):
        self.assertFalse(_is_deezer_shortlink("darude sandstorm"))


class TestLinkPatterns(unittest.TestCase):
    def test_spotify_track_url_matches(self):
        match = SPOTIFY_RE.search("https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC?si=abc")
        self.assertIsNotNone(match)
        self.assertEqual(match.groups(), ('track', '4uLU6hMCjMI75M1A2tKUQC'))

    def test_spotify_playlist_with_intl_prefix_matches(self):
        match = SPOTIFY_RE.search("https://open.spotify.com/intl-de/playlist/37i9dQZF1DXcBWIGoYBM5M")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), 'playlist')

    def test_deezer_track_url_matches(self):
        match = DEEZER_RE.search("https://www.deezer.com/de/track/123456789")
        self.assertIsNotNone(match)
        self.assertEqual(match.groups(), ('track', '123456789'))

    def test_plain_youtube_url_does_not_match_either(self):
        query = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.assertIsNone(SPOTIFY_RE.search(query))
        self.assertIsNone(DEEZER_RE.search(query))


if __name__ == '__main__':
    unittest.main()
