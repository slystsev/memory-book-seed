import unittest

from powx import db
from powx.cluster import recluster


class ReclusterTest(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(":memory:")
        for sid, side, tier in [("koord", "ua", 1), ("mod", "ru", 1), ("echo", "ua", 2), ("wiki", "neutral", 3)]:
            db.upsert_source(self.con, {"id": sid, "kind": "telegram", "handle": sid, "side": side, "tier": tier})
        rows = [  # source, ext, published_at, hash, ua, ru, exchange_date
            ("koord", "1", "2024-01-03T10:00:00+00:00", "h1", 230, None, None),
            ("mod", "1", "2024-01-03T11:00:00+00:00", "h2", None, 248, None),
            ("echo", "1", "2024-01-03T12:00:00+00:00", "h1", 230, None, None),   # same text -> copy
            ("koord", "2", "2024-02-01T10:00:00+00:00", "h3", 100, None, None),
            # retrospective post a week later that names the exchange date -> joins Jan 3 event
            ("echo", "2", "2024-01-10T10:00:00+00:00", "h4", 230, 248, "2024-01-03"),
            # wiki paragraph without a date: must not found an event
            ("wiki", "1", "2026-11-04T12:00:00+00:00", "h5", 999, None, None),
        ]
        for src, ext, at, h, ua, ru, ex in rows:
            db.insert_mention(self.con, dict(
                source_id=src, external_id=ext, url=f"https://t.me/{src}/{ext}", published_at=at,
                text="x", text_hash=h, forwarded_from=None, kind="pow", n_to_ua=ua, n_to_ru=ru,
                exchange_date=ex))

    def q(self, sql):
        return [tuple(r) for r in self.con.execute(sql)]

    def test_events_written_and_idempotent(self):
        recluster(self.con)
        recluster(self.con)
        self.assertEqual(
            self.q("SELECT date, n_to_ua, n_to_ru, mention_count, source_count, primary_url FROM events ORDER BY date"),
            [("2024-01-03", 230, 248, 4, 3, "https://t.me/koord/1"),
             ("2024-02-01", 100, None, 1, 1, "https://t.me/koord/2")])

    def test_undated_tier3_left_unassigned(self):
        recluster(self.con)
        self.assertEqual(self.q("SELECT event_id FROM mentions WHERE source_id='wiki'"), [(None,)])

    def test_manual_override_survives(self):
        recluster(self.con)
        self.con.execute("UPDATE events SET n_to_ua=231, manual_override=1 WHERE date='2024-01-03'")
        self.con.commit()
        recluster(self.con)
        self.assertEqual(self.q("SELECT n_to_ua FROM events WHERE date='2024-01-03'"), [(231,)])
        self.assertEqual(self.q("SELECT count(*) FROM events"), [(2,)])
