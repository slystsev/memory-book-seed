import json
import unittest
from types import SimpleNamespace as NS

from powx import db, llm_batch

AT = "2024-01-03T10:00:00+00:00"
OK = {"report_type": "exchange_event", "returned_to_ukraine": 84, "returned_to_russia": 84,
      "civilians_to_ukraine": None, "exchange_date": "2024-01-03", "quote": "84 на 84"}


class FakeBatches:
    def __init__(self):
        self.created, self.status, self.out = [], "in_progress", []

    def create(self, requests):
        self.created.append(requests)
        return NS(id="msgbatch_1")

    def retrieve(self, bid):
        return NS(id=bid, processing_status=self.status)

    def results(self, bid):
        return iter(self.out)


def msg(obj):
    return NS(stop_reason="end_turn", model="m", content=[NS(type="text", text=json.dumps(obj))])


class BatchTest(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(":memory:")
        db.upsert_source(self.con, {"id": "k", "kind": "telegram", "handle": "k", "side": "ua", "tier": 1})
        for ext in ("1", "2", "3"):
            db.insert_mention(self.con, dict(source_id="k", external_id=ext, url="u", published_at=AT,
                                             text="обмін " + ext, text_hash=ext, forwarded_from=None,
                                             kind="candidate", n_to_ua=None, n_to_ru=None,
                                             llm_status="pending"))
        self.batches = FakeBatches()
        self.client = NS(messages=NS(batches=self.batches))

    def statuses(self):
        return [r[0] for r in self.con.execute("SELECT llm_status FROM mentions ORDER BY id")]

    def test_submit(self):
        self.assertEqual(llm_batch.submit(self.con, self.client), "msgbatch_1")
        reqs = self.batches.created[0]
        self.assertEqual([r["custom_id"] for r in reqs], ["1", "2", "3"])
        self.assertIn("обмін 1", reqs[0]["params"]["messages"][0]["content"])
        self.assertEqual(self.statuses(), ["batched"] * 3)
        self.assertEqual(tuple(self.con.execute("SELECT id, status, size FROM llm_batches").fetchone()),
                         ("msgbatch_1", "submitted", 3))
        self.assertIsNone(llm_batch.submit(self.con, self.client))      # nothing pending left

    def test_collect(self):
        llm_batch.submit(self.con, self.client)
        self.assertEqual(llm_batch.collect(self.con, self.client), 0)  # still in progress
        self.batches.status = "ended"
        self.batches.out = [   # any order
            NS(custom_id="3", result=NS(type="errored")),
            NS(custom_id="1", result=NS(type="succeeded", message=msg(OK))),
            NS(custom_id="2", result=NS(type="expired")),
        ]
        self.assertEqual(llm_batch.collect(self.con, self.client), 1)
        self.assertEqual(self.statuses(), ["done", "pending", "pending"])
        self.assertEqual(tuple(self.con.execute("SELECT kind, n_to_ua FROM mentions WHERE id=1").fetchone()),
                         ("pow", 84))
        self.assertEqual(self.con.execute("SELECT status FROM llm_batches").fetchone()[0], "collected")
