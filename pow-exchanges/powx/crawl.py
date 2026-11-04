"""Crawl sources into mentions, run LLM extraction (update mode), recluster.

    python -m powx.crawl backfill   # walk every source back to 2022-02-24 (resumable)
    python -m powx.crawl update     # newest posts + synchronous LLM extraction
"""
import argparse
import json
import logging
import pathlib
from datetime import datetime, timezone

from powx import db, llm
from powx import http as http_mod
from powx.cluster import recluster
from powx.fetchers import rss, telegram, wikipedia
from powx.prefilter import is_candidate, text_hash

START = "2022-02-24T00:00:00+00:00"
log = logging.getLogger("powx.crawl")


def ingest(con, src, items):
    """Store raw items; candidates wait for the LLM, the rest are final as 'other'."""
    new = 0
    for it in items:
        cand = is_candidate(it.text)
        new += db.insert_mention(con, dict(
            source_id=src["id"], external_id=it.external_id, url=it.url, published_at=it.published_at,
            text=it.text, text_hash=text_hash(it.text), forwarded_from=it.forwarded_from,
            kind="candidate" if cand else "other", n_to_ua=None, n_to_ru=None,
            llm_status="pending" if cand else "skipped"))
    return new


def _bump_newest(con, src_id, page):
    cur = db.get_source(con, src_id)["cursor_newest"]
    return str(max(int(cur or 0), int(page[-1].external_id)))


def _telegram(con, src, mode, http):
    row, new = db.get_source(con, src["id"]), 0
    if mode == "backfill" and not row["backfill_done"]:
        for page in telegram.iter_older(src["handle"], row["cursor_oldest"], http, START):
            new += ingest(con, src, page)
            db.set_cursor(con, src["id"], cursor_oldest=page[0].external_id,
                          cursor_newest=_bump_newest(con, src["id"], page))
        db.set_cursor(con, src["id"], backfill_done=1)
    else:
        for page in telegram.iter_newer(src["handle"], row["cursor_newest"], http):
            new += ingest(con, src, page)
            db.set_cursor(con, src["id"], cursor_newest=_bump_newest(con, src["id"], page))
    return new


def crawl_source(con, src, mode, http):
    if src["kind"] == "telegram":
        return _telegram(con, src, mode, http)
    if src["kind"] == "rss":
        return ingest(con, src, rss.fetch(src["handle"], http))
    if src["kind"] == "wikipedia":
        return ingest(con, src, wikipedia.fetch(src["handle"], http))
    raise ValueError(f"unknown source kind {src['kind']}")


def sync_extractor(con):
    llm.process_pending(con, llm.make_client())


def run(con, sources, mode, http=http_mod.get, extractor=sync_extractor):
    """Backfill leaves candidates pending for the batch path (powx.llm_batch)."""
    stats = {}
    for src in sources:
        db.upsert_source(con, src)
        now = datetime.now(timezone.utc).isoformat()
        try:
            stats[src["id"]] = crawl_source(con, src, mode, http)
            db.set_cursor(con, src["id"], last_error=None, last_run_at=now)
        except Exception as e:   # one broken source must not stop the others
            log.exception("source %s failed", src["id"])
            stats[src["id"]] = 0
            db.set_cursor(con, src["id"], last_error=f"{type(e).__name__}: {e}", last_run_at=now)
    if mode == "update" and extractor:
        try:
            extractor(con)
        except Exception:
            log.exception("LLM extraction failed; rows stay pending")
    recluster(con)
    return stats


def load_sources(path):
    return json.loads(pathlib.Path(path).read_text())["sources"]


def main():
    p = argparse.ArgumentParser(prog="powx.crawl")
    p.add_argument("mode", choices=["backfill", "update"])
    p.add_argument("--db", default="powx.db")
    p.add_argument("--sources", default="sources.json")
    p.add_argument("--only", help="comma-separated source ids")
    p.add_argument("--no-llm", action="store_true", help="skip LLM extraction (update mode)")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    sources = load_sources(a.sources)
    if a.only:
        keep = set(a.only.split(","))
        sources = [s for s in sources if s["id"] in keep]
    print(run(db.connect(a.db), sources, a.mode, extractor=None if a.no_llm else sync_extractor))


if __name__ == "__main__":
    main()
