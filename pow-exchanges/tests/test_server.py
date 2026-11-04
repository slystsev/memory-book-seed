import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from powx import db, server
from powx.cluster import recluster


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = os.path.join(tempfile.mkdtemp(), "t.db")
        con = db.connect(cls.path)
        db.upsert_source(con, {"id": "koord", "kind": "telegram", "handle": "koord", "side": "ua", "tier": 1})
        for ext, at, ua in [("1", "2024-01-03T10:00:00+00:00", 230), ("2", "2024-02-01T10:00:00+00:00", 100)]:
            db.insert_mention(con, dict(source_id="koord", external_id=ext, url=f"https://t.me/koord/{ext}",
                                        published_at=at, text="x" + ext, text_hash=ext, forwarded_from=None,
                                        kind="pow", n_to_ua=ua, n_to_ru=None))
        db.insert_mention(con, dict(source_id="koord", external_id="3", url="u", published_at="2024-02-02T00:00:00+00:00",
                                    text="обмін", text_hash="3", forwarded_from=None, kind="candidate",
                                    n_to_ua=None, n_to_ru=None, llm_status="pending"))
        recluster(con)
        con.close()
        cls.httpd = server.make_server(cls.path, port=0)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def get(self, p):
        return json.load(urllib.request.urlopen(self.base + p))

    def test_stats(self):
        self.assertEqual(self.get("/api/stats"), {"exchanges": 2, "to_ua": 330, "to_ru": 0,
                                                  "last_date": "2024-02-01", "mentions": 2, "sources": 1,
                                                  "pending_llm": 1})

    def test_monthly_events_mentions(self):
        self.assertEqual([r["month"] for r in self.get("/api/monthly")], ["2024-01", "2024-02"])
        ev = self.get("/api/events")[0]
        self.assertEqual((ev["date"], ev["primary_url"], ev["primary_tier"]), ("2024-02-01", "https://t.me/koord/2", 1))
        ms = self.get(f"/api/events/{ev['id']}/mentions")
        self.assertEqual(len(ms), 1)
        self.assertIn("quote", ms[0])

    def test_sources(self):
        self.assertEqual(self.get("/api/sources")[0]["mentions"], 3)

    def test_index_health_404(self):
        self.assertIn(b"<html", urllib.request.urlopen(self.base + "/").read())
        self.assertEqual(self.get("/healthz"), {"ok": True})
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(self.base + "/nope")
