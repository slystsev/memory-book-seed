import pathlib
import unittest

from powx.fetchers import wikipedia

FIX = pathlib.Path(__file__).parent / "fixtures"
RAW = (FIX / "wiki_parse.json").read_text()     # trimmed live parse-API reply, 2026-11-04
NOW = "2026-11-04T12:00:00+00:00"


class WikiTest(unittest.TestCase):
    def setUp(self):
        self.urls = []

        def http(url):
            self.urls.append(url)
            return RAW
        self.items = wikipedia.fetch("Prisoners of war in the Russo-Ukrainian war (2022–present)", http, now=NOW)

    def test_uses_parse_api(self):
        self.assertIn("action=parse", self.urls[0])
        self.assertIn("Prisoners_of_war_in_the_Russo-Ukrainian_war", self.urls[0])

    def test_references_become_dated_items(self):
        refs = [i for i in self.items if i.external_id.startswith("wiki:ref:")]
        self.assertEqual(len(refs), 3)
        bbc = next(i for i in refs if "bbc.com" in i.url)
        self.assertEqual(bbc.published_at, "2024-09-14T12:00:00+00:00")
        self.assertIn("Russia and Ukraine exchange 206 prisoners", bbc.text)
        self.assertNotIn("^", bbc.text)

    def test_paragraphs_kept_and_unrelated_dropped(self):
        paras = [i for i in self.items if i.external_id.startswith("wiki:p:")]
        self.assertEqual(len(paras), 2)
        self.assertTrue(all(p.published_at == NOW for p in paras))
        self.assertTrue(all("[" not in p.text for p in paras))      # footnote markers stripped
        self.assertTrue(all(p.url.startswith("https://en.wikipedia.org/wiki/") for p in paras))

    def test_ids_are_stable(self):
        again = wikipedia.parse(RAW, NOW)
        self.assertEqual([i.external_id for i in again], [i.external_id for i in self.items])
