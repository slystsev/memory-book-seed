"""JSON API + dashboard, with an optional background incremental updater.

    python -m powx.server --db powx.db --port 8000 --interval 1800
"""
import argparse
import json
import logging
import pathlib
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from powx import crawl, db

STATIC = pathlib.Path(__file__).parent / "static"
log = logging.getLogger("powx.server")

QUERIES = {
    "/api/stats": ("one", """SELECT (SELECT count(*) FROM events) exchanges,
        (SELECT coalesce(sum(n_to_ua), 0) FROM events) to_ua,
        (SELECT coalesce(sum(n_to_ru), 0) FROM events) to_ru,
        (SELECT max(date) FROM events) last_date,
        (SELECT count(*) FROM mentions WHERE kind='pow') mentions,
        (SELECT count(*) FROM sources) sources,
        (SELECT count(*) FROM mentions WHERE llm_status IN ('pending','batched')) pending_llm"""),
    "/api/monthly": ("all", """SELECT substr(date, 1, 7) month, count(*) exchanges,
        coalesce(sum(n_to_ua), 0) to_ua, coalesce(sum(n_to_ru), 0) to_ru
        FROM events GROUP BY month ORDER BY month"""),
    "/api/events": ("all", """SELECT e.*, s.id source_id, s.tier primary_tier FROM events e
        LEFT JOIN mentions m ON m.id=e.primary_mention_id LEFT JOIN sources s ON s.id=m.source_id
        ORDER BY e.date DESC, e.id DESC"""),
    "/api/sources": ("all", """SELECT s.*, (SELECT count(*) FROM mentions m WHERE m.source_id=s.id) mentions
        FROM sources s ORDER BY tier, id"""),
}
MENTIONS = re.compile(r"^/api/events/(\d+)/mentions$")
MENTIONS_SQL = """SELECT m.id, m.source_id, s.tier, m.url, m.published_at, m.text, m.n_to_ua, m.n_to_ru,
    m.n_civilians_to_ua, m.forwarded_from, m.quote, m.report_type, m.llm_model
    FROM mentions m JOIN sources s ON s.id=m.source_id WHERE m.event_id=? ORDER BY m.published_at"""


def make_server(db_path, host="127.0.0.1", port=8000):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            if path == "/healthz":
                return self._send(200, {"ok": True})
            con = db.connect(db_path)
            try:
                if path in QUERIES:
                    kind, sql = QUERIES[path]
                    rows = con.execute(sql).fetchall()
                    return self._send(200, dict(rows[0]) if kind == "one" else [dict(r) for r in rows])
                if m := MENTIONS.match(path):
                    return self._send(200, [dict(r) for r in con.execute(MENTIONS_SQL, (int(m[1]),))])
                self._send(404, {"error": "not found"})
            finally:
                con.close()

        def log_message(self, fmt, *args):
            log.debug(fmt, *args)

    return ThreadingHTTPServer((host, port), Handler)


def start_updater(db_path, sources_path, interval, use_llm=True):
    def loop():
        while True:
            try:
                con = db.connect(db_path)
                stats = crawl.run(con, crawl.load_sources(sources_path), "update",
                                  extractor=crawl.sync_extractor if use_llm else None)
                log.info("update: %s", stats)
                con.close()
            except Exception:
                log.exception("update failed")
            time.sleep(interval)
    threading.Thread(target=loop, daemon=True, name="updater").start()


def main():
    p = argparse.ArgumentParser(prog="powx.server")
    p.add_argument("--db", default="powx.db")
    p.add_argument("--sources", default="sources.json")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--interval", type=int, default=1800, help="seconds between updates; 0 = off")
    p.add_argument("--no-llm", action="store_true", help="updater crawls but skips LLM extraction")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    db.connect(a.db).close()
    if a.interval:
        start_updater(a.db, a.sources, a.interval, use_llm=not a.no_llm)
    srv = make_server(a.db, a.host, a.port)
    log.info("serving on http://%s:%s", a.host, srv.server_address[1])
    srv.serve_forever()


if __name__ == "__main__":
    main()
