import json
import unittest
from types import SimpleNamespace as NS

from powx import db, llm


def reply(obj, stop="end_turn"):
    return NS(stop_reason=stop, model="m", content=[NS(type="text", text=json.dumps(obj))])


class FakeMessages:
    def __init__(self, resp):
        self.resp, self.calls = resp, []

    def create(self, **kw):
        self.calls.append(kw)
        return self.resp(kw) if callable(self.resp) else self.resp


def client(resp):
    m = FakeMessages(resp)
    return NS(messages=m, beta=NS(messages=m))


OK = {"report_type": "exchange_event", "returned_to_ukraine": 84, "returned_to_russia": None,
      "civilians_to_ukraine": None, "exchange_date": "2024-01-03",
      "quote": "Додому повертаються 84 українці."}
AT = "2024-01-03T10:00:00+00:00"


class LlmTest(unittest.TestCase):
    def test_request_shape_haiku(self):
        c = client(reply(OK))
        llm.extract(c, "текст", side="ua", published_at=AT, model="claude-haiku-5-5")
        kw = c.messages.calls[0]
        self.assertEqual(kw["model"], "claude-haiku-5-5")
        self.assertEqual(kw["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(kw["output_config"]["effort"], "low")
        self.assertNotIn("fallbacks", kw)          # Haiku has no server-side fallback
        self.assertIn("текст", kw["messages"][0]["content"])
        self.assertIn("Publisher side: ua", kw["messages"][0]["content"])

    def test_request_shape_opus_uses_fallbacks(self):
        c = client(reply(OK))
        llm.extract(c, "t", "ua", AT, model="claude-opus-5-5")
        kw = c.messages.calls[0]
        self.assertEqual(kw["fallbacks"], "default")
        self.assertIn("server-side-fallback-2026-07-01", kw["betas"])

    def test_maps_exchange_event(self):
        r = llm.extract(client(reply(OK)), "t", "ua", AT)
        self.assertEqual((r["kind"], r["n_to_ua"], r["n_to_ru"], r["exchange_date"], r["llm_status"]),
                         ("pow", 84, None, "2024-01-03", "done"))

    def test_cumulative_total_not_counted(self):
        r = llm.extract(client(reply(dict(OK, report_type="cumulative_total", returned_to_ukraine=4000))),
                        "t", "ua", AT)
        self.assertEqual(r["kind"], "other")

    def test_bodies(self):
        r = llm.extract(client(reply(dict(OK, report_type="bodies_repatriation"))), "t", "ua", AT)
        self.assertEqual(r["kind"], "bodies")

    def test_refusal_and_truncation_marked_failed(self):
        for stop in ("refusal", "max_tokens"):
            r = llm.extract(client(reply(OK, stop=stop)), "t", "ua", AT)
            self.assertEqual(r["llm_status"], "failed")

    def test_garbage_marked_failed(self):
        bad = NS(stop_reason="end_turn", model="m", content=[NS(type="text", text="not json")])
        self.assertEqual(llm.extract(client(bad), "t", "ua", AT)["llm_status"], "failed")

    def test_bad_date_dropped(self):
        r = llm.extract(client(reply(dict(OK, exchange_date="3 Jan"))), "t", "ua", AT)
        self.assertIsNone(r["exchange_date"])


class ProcessPendingTest(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(":memory:")
        db.upsert_source(self.con, {"id": "k", "kind": "telegram", "handle": "k", "side": "ua", "tier": 1})
        for ext in ("1", "2", "3"):
            db.insert_mention(self.con, dict(source_id="k", external_id=ext, url="u", published_at=AT,
                                             text="обмін " + ext, text_hash=ext, forwarded_from=None,
                                             kind="candidate", n_to_ua=None, n_to_ru=None,
                                             llm_status="pending"))
        self.con.execute("UPDATE mentions SET llm_attempts=3 WHERE external_id='3'")

    def test_processes_pending_and_respects_attempt_cap(self):
        n = llm.process_pending(self.con, client(reply(OK)))
        self.assertEqual(n, 2)
        rows = [tuple(r) for r in self.con.execute(
            "SELECT external_id, kind, llm_status, n_to_ua, quote FROM mentions ORDER BY external_id")]
        self.assertEqual(rows[0], ("1", "pow", "done", 84, OK["quote"]))
        self.assertEqual(rows[2], ("3", "candidate", "pending", None, None))
