import json
import unittest

from powx import crawl, db


def tg(ids, text="Обмін полоненими: додому повертаються 84 українці", date="2024-01-03T10:00:00+00:00"):
    return "".join(
        f'<div class="tgme_widget_message" data-post="koord/{i}"><div class="tgme_widget_message_text">{text}</div>'
        f'<a class="tgme_widget_message_date"><time datetime="{date}"></time></a></div>' for i in ids)


SOURCES = [{"id": "koord", "kind": "telegram", "handle": "koord", "side": "ua", "tier": 1}]


def fake_extractor(con):   # stands in for the LLM step
    with con:
        con.execute("UPDATE mentions SET kind='pow', n_to_ua=84, llm_status='done' WHERE llm_status='pending'")


class CrawlTest(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(":memory:")

    def count(self, where):
        return self.con.execute(f"SELECT count(*) FROM mentions WHERE {where}").fetchone()[0]

    def test_backfill_then_update(self):
        pages = {"https://t.me/s/koord": tg([20, 21]), "https://t.me/s/koord?before=20": tg([10]),
                 "https://t.me/s/koord?before=10": ""}
        crawl.run(self.con, SOURCES, "backfill", http=pages.__getitem__, extractor=fake_extractor)
        src = db.get_source(self.con, "koord")
        self.assertEqual((src["cursor_newest"], src["cursor_oldest"], src["backfill_done"]), ("21", "10", 1))
        self.assertEqual(self.count("llm_status='pending'"), 3)      # backfill leaves LLM to batches
        self.assertEqual(self.con.execute("SELECT count(*) FROM events").fetchone()[0], 0)

        pages["https://t.me/s/koord"] = tg([21, 22])
        stats = crawl.run(self.con, SOURCES, "update", http=pages.__getitem__, extractor=fake_extractor)
        self.assertEqual(stats["koord"], 1)
        self.assertEqual(db.get_source(self.con, "koord")["cursor_newest"], "22")
        self.assertEqual(self.count("llm_status='pending'"), 0)
        self.assertEqual(self.count("kind='pow' AND n_to_ua=84"), 4)
        self.assertEqual(self.con.execute("SELECT count(*) FROM events").fetchone()[0], 1)

    def test_backfill_resumes_from_cursor(self):
        pages = {"https://t.me/s/koord": tg([20, 21])}
        def flaky(url):
            if url not in pages:
                raise OSError("network down")
            return pages[url]
        crawl.run(self.con, SOURCES, "backfill", http=flaky)
        self.assertEqual(db.get_source(self.con, "koord")["backfill_done"], 0)
        pages.update({"https://t.me/s/koord?before=20": tg([10]), "https://t.me/s/koord?before=10": ""})
        crawl.run(self.con, SOURCES, "backfill", http=flaky)
        self.assertEqual(db.get_source(self.con, "koord")["backfill_done"], 1)
        self.assertEqual(self.count("1=1"), 3)

    def test_non_candidates_skip_llm(self):
        pages = {"https://t.me/s/koord": tg([5], text="Обстріл Харкова"), "https://t.me/s/koord?before=5": ""}
        crawl.run(self.con, SOURCES, "backfill", http=pages.__getitem__)
        self.assertEqual(tuple(self.con.execute("SELECT kind, llm_status FROM mentions").fetchone()),
                         ("other", "skipped"))

    def test_source_error_is_recorded_not_raised(self):
        def boom(url):
            raise OSError("blocked")
        crawl.run(self.con, SOURCES, "update", http=boom, extractor=None)
        self.assertIn("blocked", db.get_source(self.con, "koord")["last_error"])

    def test_sources_file_is_valid(self):
        import pathlib
        data = json.loads((pathlib.Path(__file__).parents[1] / "sources.json").read_text())
        for s in data["sources"]:
            self.assertEqual(set(s), {"id", "kind", "handle", "side", "tier"})
            self.assertIn(s["kind"], ("telegram", "rss", "wikipedia"))
