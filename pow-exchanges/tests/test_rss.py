import pathlib
import unittest

from powx.fetchers.rss import parse_feed

FIX = pathlib.Path(__file__).parent / "fixtures"

RSS = """<rss><channel><item><title>Обмін полоненими</title><link>https://ex.ua/a</link>
<guid>a-1</guid><pubDate>Wed, 03 Jan 2024 12:00:00 +0200</pubDate>
<description>&lt;p&gt;Додому повертаються 230 українців&lt;/p&gt;</description></item></channel></rss>"""
ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>urn:b</id><title>Swap</title>
<link href="https://ex.com/b"/><updated>2024-01-03T10:00:00Z</updated><summary>POW swap</summary></entry></feed>"""


class RssTest(unittest.TestCase):
    def test_rss(self):
        [i] = parse_feed(RSS)
        self.assertEqual((i.external_id, i.url, i.published_at),
                         ("a-1", "https://ex.ua/a", "2024-01-03T10:00:00+00:00"))
        self.assertEqual(i.text, "Обмін полоненими\nДодому повертаються 230 українців")

    def test_atom(self):
        [i] = parse_feed(ATOM)
        self.assertEqual((i.external_id, i.url, i.published_at),
                         ("urn:b", "https://ex.com/b", "2024-01-03T10:00:00+00:00"))

    def test_live_fixtures(self):
        """Trimmed copies of pravda.com.ua/rss/ and tass.ru/rss/v2.xml saved 2026-11-04."""
        for name, prefix in (("rss_pravda.xml", "https://www.pravda.com.ua/"),
                             ("rss_tass.xml", "https://tass.ru/")):
            items = parse_feed((FIX / name).read_text())
            self.assertEqual(len(items), 2, name)
            for i in items:
                self.assertTrue(i.url.startswith(prefix))
                self.assertTrue(i.text)
                self.assertTrue(i.published_at.endswith("+00:00"))
