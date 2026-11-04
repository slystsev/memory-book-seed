"""Backfill extraction through the Message Batches API (50 % cheaper, async, ≤ 24 h).

    python -m powx.llm_batch submit   # repeat until it prints None
    python -m powx.llm_batch collect  # repeat (e.g. every 10 min) until no batch is 'submitted'
    python -m powx.llm_batch status

Batch requests carry no server-side fallback; refusals come back as llm_status='failed' and are
retried by the synchronous path (llm.process_pending) on the next update.
"""
import argparse
import logging
from datetime import datetime, timezone

from powx import db
from powx.llm import apply, build_params, make_client, parse_message

CHUNK = 10_000
log = logging.getLogger("powx.llm_batch")


def submit(con, client, chunk=CHUNK):
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    rows = con.execute("""SELECT m.id, m.text, m.published_at, s.side FROM mentions m
                          JOIN sources s ON s.id=m.source_id WHERE m.llm_status='pending'
                          ORDER BY m.id LIMIT ?""", (chunk,)).fetchall()
    if not rows:
        return None
    batch = client.messages.batches.create(requests=[
        Request(custom_id=str(r["id"]),
                params=MessageCreateParamsNonStreaming(**build_params(r["text"], r["side"], r["published_at"])))
        for r in rows])
    with con:
        con.execute("INSERT INTO llm_batches(id, created_at, status, size) VALUES(?,?,?,?)",
                    (batch.id, datetime.now(timezone.utc).isoformat(), "submitted", len(rows)))
        con.executemany("UPDATE mentions SET llm_status='batched' WHERE id=?", [(r["id"],) for r in rows])
    return batch.id


def collect(con, client):
    collected = 0
    for (bid,) in con.execute("SELECT id FROM llm_batches WHERE status='submitted'").fetchall():
        if client.messages.batches.retrieve(bid).processing_status != "ended":
            continue
        for res in client.messages.batches.results(bid):     # any order -> key by custom_id
            mid = int(res.custom_id)
            if res.result.type == "succeeded":
                apply(con, mid, parse_message(res.result.message))
            else:
                apply(con, mid, {"llm_status": "pending"})
        with con:
            con.execute("UPDATE llm_batches SET status='collected' WHERE id=?", (bid,))
        collected += 1
    return collected


def status(con):
    rows = con.execute("SELECT llm_status, count(*) FROM mentions GROUP BY llm_status").fetchall()
    batches = con.execute("SELECT status, count(*) FROM llm_batches GROUP BY status").fetchall()
    return {"mentions": {r[0]: r[1] for r in rows}, "batches": {r[0]: r[1] for r in batches}}


def main():
    p = argparse.ArgumentParser(prog="powx.llm_batch")
    p.add_argument("action", choices=["submit", "collect", "status"])
    p.add_argument("--db", default="powx.db")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO)
    con = db.connect(a.db)
    if a.action == "status":
        print(status(con))
    elif a.action == "submit":
        print(submit(con, make_client()))
    else:
        print(collect(con, make_client()))


if __name__ == "__main__":
    main()
