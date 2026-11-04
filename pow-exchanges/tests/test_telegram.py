import pathlib
import unittest

from powx.fetchers import telegram

FIX = pathlib.Path(__file__).parent / "fixtures"


def page(ids, date="2024-01-03T10:00:00+00:00", prev=None):
    posts = "".join(
        f'<div class="tgme_widget_message" data-post="c/{i}"><div class="tgme_widget_message_text">x</div>'
        f'<a class="tgme_widget_message_date"><time datetime="{date}"></time></a></div>' for i in ids)
    link = f'<link rel="prev" href="/s/c?before={prev}">' if prev else ""
    return f"<html><head>{link}</head><body>{posts}</body></html>"


class ParseTest(unittest.TestCase):
    def test_synthetic(self):
        html = page([101]).replace(
            '<div class="tgme_widget_message_text">',
            '<a class="tgme_widget_message_forwarded_from_name" href="https://t.me/V_Zelenskiy_official/9000">Z</a>'
            '<div class="tgme_widget_message_text">')
        html += '<div class="tgme_widget_message" data-post="c/102"><div class="tgme_widget_message_text">no date</div></div>'
        items, prev = telegram.parse_page(html)
        self.assertEqual([i.external_id for i in items], ["101"])          # undated skipped
        self.assertEqual(items[0].forwarded_from, "https://t.me/V_Zelenskiy_official/9000")
        self.assertEqual(items[0].url, "https://t.me/c/101")
        self.assertIsNone(prev)

    def test_utc_normalization(self):
        items, _ = telegram.parse_page(page([1], date="2024-01-03T12:00:00+02:00"))
        self.assertEqual(items[0].published_at, "2024-01-03T10:00:00+00:00")

    def test_live_fixture(self):
        """Saved from https://t.me/s/Koord_Shtab on 2026-11-04."""
        items, prev = telegram.parse_page((FIX / "tg_live.html").read_text())
        self.assertGreaterEqual(len(items), 5)
        self.assertTrue(all(i.url.startswith("https://t.me/Koord_shtab/") for i in items))
        self.assertTrue(all(i.text for i in items))
        self.assertEqual(prev, "23758")
        self.assertEqual(items[-1].published_at, "2026-11-04T10:31:44+00:00")


class PaginationTest(unittest.TestCase):
    def test_iter_older_follows_prev_link(self):
        pages = {"https://t.me/s/c": page([30, 31], prev="25"),
                 "https://t.me/s/c?before=25": page([10, 11]),
                 "https://t.me/s/c?before=10": ""}
        got = [[i.external_id for i in p] for p in telegram.iter_older("c", None, pages.__getitem__, "2022-02-24")]
        self.assertEqual(got, [["30", "31"], ["10", "11"]])

    def test_iter_older_stops_at_start_date(self):
        pages = {"https://t.me/s/c": page([5], date="2021-01-01T00:00:00+00:00")}
        self.assertEqual(len(list(telegram.iter_older("c", None, pages.__getitem__, "2022-02-24"))), 1)

    def test_iter_older_stops_without_progress(self):
        pages = {"https://t.me/s/c?before=10": page([10, 11])}   # no older posts than cursor
        self.assertEqual(len(list(telegram.iter_older("c", "10", pages.__getitem__, "2022-02-24"))), 1)

    def test_iter_newer_stops_at_cursor(self):
        pages = {"https://t.me/s/c": page([50, 51]), "https://t.me/s/c?before=50": page([48, 49])}
        got = [[i.external_id for i in p] for p in telegram.iter_newer("c", "48", pages.__getitem__)]
        self.assertEqual(got, [["50", "51"], ["49"]])

    def test_iter_newer_without_cursor_takes_one_page(self):
        pages = {"https://t.me/s/c": page([50, 51])}
        self.assertEqual(len(list(telegram.iter_newer("c", None, pages.__getitem__))), 1)
