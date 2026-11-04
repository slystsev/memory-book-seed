import unittest
from powx import db

SRC = {"id": "koordshtab", "kind": "telegram", "handle": "koordshtab", "side": "ua", "tier": 1}


def mention(**kw):
    m = {"source_id": "koordshtab", "external_id": "1", "url": "https://t.me/koordshtab/1",
         "published_at": "2024-01-03T10:00:00+00:00", "text": "t", "text_hash": "h",
         "forwarded_from": None, "kind": "pow", "n_to_ua": 230, "n_to_ru": None}
    m.update(kw)
    return m


class DbTest(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(":memory:")
        db.upsert_source(self.con, SRC)

    def test_insert_is_idempotent_per_source(self):
        self.assertTrue(db.insert_mention(self.con, mention()))
        self.assertFalse(db.insert_mention(self.con, mention(text="edited")))
        self.assertEqual(self.con.execute("SELECT count(*) FROM mentions").fetchone()[0], 1)

    def test_defaults(self):
        db.insert_mention(self.con, mention())
        row = self.con.execute("SELECT llm_status, llm_attempts FROM mentions").fetchone()
        self.assertEqual(tuple(row), ("skipped", 0))

    def test_upsert_source_keeps_cursors(self):
        db.set_cursor(self.con, "koordshtab", cursor_oldest="50", backfill_done=1)
        db.upsert_source(self.con, dict(SRC, tier=2))
        row = db.get_source(self.con, "koordshtab")
        self.assertEqual((row["tier"], row["cursor_oldest"], row["backfill_done"]), (2, "50", 1))
