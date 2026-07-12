import unittest

from utils.music_utils import resolve_stream_url


class TestResolveStreamUrl(unittest.IsolatedAsyncioTestCase):
    """Direkte (Nicht-.m3u) Stream-URLs müssen unverändert durchgereicht werden, ohne
    einen HTTP-Request auszulösen - nur .m3u/.m3u8-Links werden aufgelöst."""

    async def test_direct_stream_url_is_passed_through_unchanged(self):
        url = "https://ilm.stream18.radiohost.de/ilm_iloveradio_mp3-192"
        self.assertEqual(await resolve_stream_url(url), url)

    async def test_url_with_query_string_but_no_m3u_extension_is_passed_through(self):
        url = "https://example.com/stream?token=abc"
        self.assertEqual(await resolve_stream_url(url), url)


if __name__ == '__main__':
    unittest.main()
