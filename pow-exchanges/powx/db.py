import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources(
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, handle TEXT NOT NULL,
  side TEXT NOT NULL, tier INTEGER NOT NULL,
  cursor_newest TEXT, cursor_oldest TEXT, backfill_done INTEGER NOT NULL DEFAULT 0,
  last_error TEXT, last_run_at TEXT);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, n_to_ua INTEGER, n_to_ru INTEGER,
  primary_mention_id INTEGER, primary_url TEXT, mention_count INTEGER NOT NULL,
  source_count INTEGER NOT NULL, manual_override INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS mentions(
  id INTEGER PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
  external_id TEXT NOT NULL, url TEXT, published_at TEXT NOT NULL, text TEXT NOT NULL,
  text_hash TEXT NOT NULL, forwarded_from TEXT,
  kind TEXT NOT NULL,                       -- candidate | pow | bodies | other
  n_to_ua INTEGER, n_to_ru INTEGER, n_civilians_to_ua INTEGER, exchange_date TEXT,
  report_type TEXT, quote TEXT,
  llm_status TEXT NOT NULL DEFAULT 'skipped',  -- skipped | pending | batched | done | failed
  llm_model TEXT, llm_attempts INTEGER NOT NULL DEFAULT 0,
  event_id INTEGER REFERENCES events(id),
  UNIQUE(source_id, external_id));
CREATE INDEX IF NOT EXISTS mentions_kind_time ON mentions(kind, published_at);
CREATE INDEX IF NOT EXISTS mentions_event ON mentions(event_id);
CREATE INDEX IF NOT EXISTS mentions_llm ON mentions(llm_status);
CREATE TABLE IF NOT EXISTS llm_batches(
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL, size INTEGER NOT NULL);
"""


def connect(path):
    con = sqlite3.connect(path, check_same_thread=False, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    if path != ":memory:":
        con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def upsert_source(con, s):
    with con:
        con.execute(
            """INSERT INTO sources(id, kind, handle, side, tier) VALUES(:id,:kind,:handle,:side,:tier)
               ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, handle=excluded.handle,
               side=excluded.side, tier=excluded.tier""", s)


def get_source(con, source_id):
    return con.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()


def set_cursor(con, source_id, **fields):
    allowed = {"cursor_newest", "cursor_oldest", "backfill_done", "last_error", "last_run_at"}
    assert set(fields) <= allowed, fields
    cols = ", ".join(f"{k}=:{k}" for k in fields)
    with con:
        con.execute(f"UPDATE sources SET {cols} WHERE id=:id", dict(fields, id=source_id))


def insert_mention(con, m) -> bool:
    m = {"llm_status": "skipped", "exchange_date": None, **m}
    with con:
        cur = con.execute(
            """INSERT OR IGNORE INTO mentions(source_id, external_id, url, published_at, text,
               text_hash, forwarded_from, kind, n_to_ua, n_to_ru, exchange_date, llm_status)
               VALUES(:source_id,:external_id,:url,:published_at,:text,:text_hash,
                      :forwarded_from,:kind,:n_to_ua,:n_to_ru,:exchange_date,:llm_status)""", m)
    return cur.rowcount == 1
