"""Write clearly fake DEMO mentions into a throwaway DB, for dashboard screenshots only.

    python -m tests.fixtures.demo_seed /path/to/demo.db
"""
import random
import sys
from datetime import date, timedelta

from powx import db
from powx.cluster import recluster


def main(path):
    con = db.connect(path)
    for sid, side, tier in [("demo_ua", "ua", 1), ("demo_ru", "ru", 1), ("demo_news", "ua", 2), ("demo_ref", "neutral", 3)]:
        db.upsert_source(con, {"id": sid, "kind": "telegram", "handle": sid, "side": side, "tier": tier})
    rnd = random.Random(7)
    d, i = date(2022, 4, 1), 0
    while d < date(2026, 11, 1):
        n = rnd.choice([10, 25, 50, 75, 90, 103, 150, 200, 230])
        k = n + rnd.choice([0, 0, 0, 18])
        at = f"{d.isoformat()}T10:00:00+00:00"
        rows = [("demo_ua", n, None), ("demo_ru", n, k), ("demo_news", n, k)]
        if rnd.random() < 0.15:
            rows = [("demo_ref", n, k)]
        for sid, ua, ru in rows:
            i += 1
            db.insert_mention(con, dict(
                source_id=sid, external_id=str(i), url=f"https://example.org/demo/{i}", published_at=at,
                text=f"DEMO post {i}: exchange, {ua} returned to Ukraine", text_hash=f"demo{i}",
                forwarded_from=None, kind="pow", n_to_ua=ua, n_to_ru=ru, exchange_date=d.isoformat(),
                llm_status="done"))
        con.execute("UPDATE mentions SET quote=? WHERE external_id=?", (f"{ua} returned to Ukraine", str(i)))
        d += timedelta(days=rnd.randint(12, 45))
    con.commit()
    recluster(con)
    print(con.execute("SELECT count(*) FROM events").fetchone()[0], "demo events")


if __name__ == "__main__":
    main(sys.argv[1])
