# POW Exchange Tracker (RU–UA) Implementation Plan

## Status & live findings (2026-11-04) — read first; these override the task text below
- **Done and committed** on `claude/ecstatic-bell-yeogs6` (25 tests green): Task 0 scaffold,
  Task 1 DB, Task 2 prefilter, Task 3 LLM sync extraction, Task 3b batch extraction
  (`powx/llm_batch.py`), Task 4 Telegram fetcher (`powx/http.py`, `powx/fetchers/telegram.py`;
  `parse_page` returns `(items, prev_cursor)`; verified live: 4 pages of Koord_Shtab walked back,
  7–11 posts/page, ~90 % pass the prefilter). Not pushed yet.
- **Also done (35 tests green, last commit e3d283b):** Task 5 RSS (live fixtures
  `tests/fixtures/rss_{pravda,tass}.xml`; live: pravda 20 items / 4 candidates, TASS 100 / 9),
  Task 6 Wikipedia (prose `<p>` + `ol.references` items dated via COinS `rft.date`, url = the
  cited article; live: 37 items incl. BBC/Al Jazeera/Reuters exchange headlines), and
  `powx/http.py` now honours `Retry-After` (Wikipedia rate-limits the shared cloud IP).
- **Pushed** to `origin/claude/ecstatic-bell-yeogs6` through e3d283b.
- **Next:** Task 7 cluster (pure) → Task 8 recluster (skip tier-3 mentions without
  `exchange_date`) → Task 9 crawl + `sources.json` (verified handles only) → 10 server →
  11 dashboard → 12 docs/Docker/smoke → push. `Item` no longer carries
  `kind/n_to_ua/n_to_ru` — every source, Wikipedia included, goes through the LLM.
- **Default model is `claude-haiku-5-5`** (user's choice; `POWX_MODEL` overrides). Haiku has no
  server-side fallback, so `llm.extract` sends `fallbacks`/`betas` only for Opus/Sonnet/Fable.
- **No Anthropic credentials in this session** (`ANTHROPIC_API_KEY` unset, API → 401). Live LLM
  checks and the 200-sample cost gate are blocked until the user adds the key to the
  environment secrets; everything else is testable live.
- **Network:** t.me, en.wikipedia.org (needs a User-Agent, else 429), pravda.com.ua RSS,
  tass.ru RSS all reachable. uk./ru.wikipedia.org blocked.
- **Telegram handles verified:** `Koord_Shtab` (not `koordshtab`), `V_Zelenskiy_official`,
  `DIUkraine`, `mod_russia` → 200. `dmytro_lubinets`, `moskalkova_tatiana` and guessed variants
  → 302 (no public preview / wrong handle) — leave out of `sources.json`, list in README as
  "ask the user for the correct handle". Do not guess more handles.
- **Telegram markup verified** on a live page: `div.tgme_widget_message[data-post]`,
  `.tgme_widget_message_text`, `.tgme_widget_message_date time[datetime]` (UTC). A page can
  yield few parsed posts (albums/service messages), so paginate with the page's
  `<link rel="prev" href="/s/<ch>?before=N">` when present, falling back to the oldest id.
  Save the live page as `tests/fixtures/tg_live.html` and add a parse test on it.
  Note: Koord_Shtab mentions captivity in almost every post → most posts pass the prefilter
  (≈24k posts; with Haiku via Batches still ≈ $1–2 total).
- **Wikipedia replaces Task 6's table parser:** the en article
  "Prisoners of war in the Russo-Ukrainian war (2022–present)" has **no wikitable**; exchanges
  are prose in section "Prisoner and human remains exchanges". New `fetchers/wikipedia.py`:
  parse API (with User-Agent), split that section (and any `<p>`/`<li>` in the article
  mentioning "exchang"/"swap") into paragraph `Item`s (`external_id = "wiki:" + text_hash`,
  `published_at` = fetch time, url = article URL) → normal prefilter → LLM, tier 3. Tier 3 is
  never primary while tier 1/2 exists; such events show "no primary source found".
  Clustering of a Wikipedia paragraph relies on the LLM's `exchange_date`; a paragraph with
  only a month ("September 2024") gets `exchange_date=null` and simply attaches or stays
  unassigned (number-less/undated mentions never found events — but a dated-by-fetch-time
  wiki paragraph must not found an event either: in `recluster`, skip tier-3 mentions without
  `exchange_date`).
- **Remaining order:** Task 3b batch → Task 4 Telegram (+ live fixture) → Task 5 RSS (test on
  live feeds too) → Task 6 Wikipedia (prose version above) → Tasks 7–12 as written → live
  smoke: `crawl update` against real sources with the LLM step stubbed until a key exists.
- **Task 13 (new, after the user confirms):** GitHub Actions workflow (tests on push) and a
  VPS setup section (self-hosted runner + Docker deploy + scheduled update).

> **For Claude:** Execute this plan task-by-task (superpowers `executing-plans` style): for every
> task follow the steps literally — failing test → run → minimal code → run → commit. No step
> skipping, no batching of commits. Stop and report if a test fails for an unexpected reason.

**Goal:** A self-hosted web service that scrapes past and new mentions of Russia–Ukraine
prisoner-of-war exchanges, stores them in SQLite, extracts the numbers, merges duplicate mentions
into exchange events, picks the primary (original) source of each event, and shows exchange
counts on a dashboard page.

**Architecture:** Fetchers (Telegram public web preview `t.me/s/<channel>`, RSS/Atom, Wikipedia
MediaWiki API) produce raw `Item`s → a broad, recall-oriented **keyword prefilter** (cheap, only
decides "send to LLM or not") → `db` stores mentions (unique per source) with
`llm_status='pending'` → **`llm` extraction with Claude** (structured JSON output: report type,
per-side numbers, exchange date, supporting quote) — synchronous for incremental updates,
**Message Batches API (50 % cheaper)** for the backfill → `cluster` groups POW mentions into events
(36 h window + number compatibility), computes consensus numbers and the primary source →
`server` (stdlib `ThreadingHTTPServer`) serves JSON API + one static dashboard page, and runs an
incremental `update` crawl on a background timer. `backfill` walks every source back to
2022-02-24, resumable via per-source cursors.

**Tech stack:** Python 3.13, stdlib (`sqlite3`, `urllib`, `http.server`, `xml.etree`,
`unittest`), `beautifulsoup4` + `lxml` (already installed), official `anthropic` SDK. Vanilla
HTML/JS/SVG dashboard. No framework, no ORM (YAGNI).

**LLM settings:** model from env `POWX_MODEL`, default `claude-opus-5-5` (the current default
model); `claude-haiku-5-5` is the cheap alternative — the user chooses, the code doesn't
downgrade on its own. `output_config.effort="low"` (simple extraction), structured outputs via
`output_config.format` (JSON schema), server-side refusal fallback (`fallbacks: "default"`,
beta `server-side-fallback-2026-07-01`) on synchronous calls. Auth: the SDK's default credential
chain (`ANTHROPIC_API_KEY` or `ant auth login`). Rough backfill cost estimate (to be measured on
the first 200 posts before launching the full batch): ~20k candidate posts × ~700 input /
~150 output tokens → Opus 5.5 via Batches ≈ $55, Haiku 5.5 via Batches ≈ $1.5. Incremental:
cents per day. Tests never call the API — they use a fake client.

**Location:** `pow-exchanges/` inside this repo, branch `claude/ecstatic-bell-yeogs6`. It is
independent of the memory-book pipeline — do not touch `sources/ wiki/ book/ build/`.

**Known environment limit:** this cloud session's proxy blocks `t.me` and `wikipedia.org`.
Every fetcher is tested against fixture HTML/XML/JSON that mirrors the real markup; the first
live run happens on the user's machine (documented in README). Do not claim live scraping works.

**Conventions for every task**
- Run tests from `pow-exchanges/`: `python -m unittest -v`
- Commit after each green task: `git add pow-exchanges && git commit -m "<msg>"` (message ends
  with the session's Co-Authored-By / Claude-Session lines).
- Datetimes stored as UTC ISO-8601 strings (`2024-01-03T10:00:00+00:00`).

---

### Task 0: Scaffold + save this plan

**Files:**
- Create: `pow-exchanges/docs/plans/2026-11-04-pow-exchange-tracker.md` (copy of this plan)
- Create: `pow-exchanges/requirements.txt`, `pow-exchanges/powx/__init__.py`,
  `pow-exchanges/powx/fetchers/__init__.py`, `pow-exchanges/tests/__init__.py`,
  `pow-exchanges/.gitignore`

**Step 1:** create files.
```
# requirements.txt
beautifulsoup4>=4.12
lxml>=5
anthropic>=1.0
```
```
# .gitignore
*.db
*.db-wal
*.db-shm
__pycache__/
```
`__init__.py` files are empty.

**Step 2:** `cd pow-exchanges && python -m unittest -v` → Expected: `Ran 0 tests … OK`.

**Step 3:** commit `powx: scaffold POW exchange tracker + implementation plan`.

---

### Task 1: Shared model + DB layer

**Files:**
- Create: `powx/models.py`, `powx/db.py`
- Test: `tests/test_db.py`

**Step 1: failing test**
```python
# tests/test_db.py
import unittest
from powx import db

SRC = {"id": "koordshtab", "kind": "telegram", "handle": "koordshtab", "side": "ua", "tier": 1}

def mention(**kw):
    m = {"source_id": "koordshtab", "external_id": "1", "url": "https://t.me/koordshtab/1",
         "published_at": "2024-01-03T10:00:00+00:00", "text": "t", "text_hash": "h",
         "forwarded_from": None, "kind": "pow", "n_to_ua": 230, "n_to_ru": None}
    m.update(kw); return m

class DbTest(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(":memory:")
        db.upsert_source(self.con, SRC)

    def test_insert_is_idempotent_per_source(self):
        self.assertTrue(db.insert_mention(self.con, mention()))
        self.assertFalse(db.insert_mention(self.con, mention(text="edited")))
        self.assertEqual(self.con.execute("SELECT count(*) FROM mentions").fetchone()[0], 1)

    def test_upsert_source_keeps_cursors(self):
        db.set_cursor(self.con, "koordshtab", cursor_oldest="50", backfill_done=1)
        db.upsert_source(self.con, dict(SRC, tier=2))
        row = db.get_source(self.con, "koordshtab")
        self.assertEqual((row["tier"], row["cursor_oldest"], row["backfill_done"]), (2, "50", 1))
```

**Step 2:** run → FAIL (`ImportError: cannot import name 'db'`).

**Step 3: implementation**
```python
# powx/models.py
from dataclasses import dataclass

@dataclass
class Item:
    """One raw post/article/row produced by a fetcher (before classification)."""
    external_id: str
    url: str
    published_at: str            # UTC ISO-8601
    text: str
    forwarded_from: str | None = None
    kind: str | None = None      # pre-set by structured sources (wikipedia)
    n_to_ua: int | None = None
    n_to_ru: int | None = None
```
```python
# powx/db.py
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
  text_hash TEXT NOT NULL, forwarded_from TEXT, kind TEXT NOT NULL,   -- candidate|pow|bodies|other
  n_to_ua INTEGER, n_to_ru INTEGER, n_civilians_to_ua INTEGER, exchange_date TEXT,
  report_type TEXT, quote TEXT, llm_status TEXT NOT NULL DEFAULT 'skipped',  -- skipped|pending|batched|done|failed
  llm_model TEXT, llm_attempts INTEGER NOT NULL DEFAULT 0,
  event_id INTEGER REFERENCES events(id),
  UNIQUE(source_id, external_id));
CREATE INDEX IF NOT EXISTS mentions_kind_time ON mentions(kind, published_at);
CREATE INDEX IF NOT EXISTS mentions_event ON mentions(event_id);
CREATE INDEX IF NOT EXISTS mentions_llm ON mentions(llm_status);
CREATE TABLE IF NOT EXISTS llm_batches(id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
  status TEXT NOT NULL, size INTEGER NOT NULL);
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
```

**Step 4:** run → PASS (2 tests). **Step 5:** commit `powx: SQLite schema and mention storage`.

---

### Task 2: Keyword prefilter + text hash (decides only "send to the LLM or not")

**Files:** Create `powx/prefilter.py`; Test `tests/test_prefilter.py`

The prefilter is tuned for **recall**: false positives cost one cheap LLM call, false negatives
lose data. It never extracts numbers.

**Step 1: failing test**
```python
# tests/test_prefilter.py
import unittest
from powx.prefilter import is_candidate, text_hash

class PrefilterTest(unittest.TestCase):
    def test_candidates_in_three_languages(self):
        for t in ["Відбувся 51-й обмін полоненими. Додому повертаються 84 українці.",
                  "Возвращены 150 российских военнослужащих",
                  "Russia and Ukraine swapped 1,000 POWs",
                  "Україні повернули тіла 909 загиблих",
                  "Ще 12 наших захисників вдома"]:
            self.assertTrue(is_candidate(t), t)

    def test_unrelated(self):
        self.assertFalse(is_candidate("Обстріл Харкова: є поранені"))
        self.assertFalse(is_candidate(""))

    def test_hash_ignores_case_whitespace_urls(self):
        self.assertEqual(text_hash("Обмін  відбувся https://t.me/x/1"), text_hash("обмін відбувся"))
```

**Step 2:** run → FAIL (ImportError).

**Step 3: implementation**
```python
# powx/prefilter.py
import hashlib, re

KEYWORDS = re.compile(
    r"обмін|обмен|exchang|swap|полон|плен|\bpows?\b|prisoner|captiv|"
    r"повернул|повертаються|вернул|возвращен|вдома|додому|returned home|brought home|"
    r"тіла|тела|bodies|репатріац|репатриац", re.I)

def is_candidate(text: str) -> bool:
    return bool(text and KEYWORDS.search(text))

def text_hash(text: str) -> str:
    t = re.sub(r"https?://\S+", " ", text.lower())
    t = re.sub(r"\W+", " ", t).strip()
    return hashlib.sha1(t.encode()).hexdigest()
```

**Step 4:** PASS. **Step 5:** commit `powx: recall-oriented keyword prefilter`.

---

### Task 3: LLM extraction with Claude (synchronous path)

**Files:** Create `powx/llm.py`; Test `tests/test_llm.py`

Every candidate mention is sent to Claude, which returns schema-valid JSON:

| field | meaning |
|---|---|
| `report_type` | `exchange_event` (reports a specific exchange) · `cumulative_total` ("since 2022 we returned 4,000") · `negotiation_or_plan` · `bodies_repatriation` · `other` |
| `returned_to_ukraine` / `returned_to_russia` | people returned to each side in **this** exchange; `null` if not stated — never guessed |
| `civilians_to_ukraine` | civilians among those returned to Ukraine, if stated |
| `exchange_date` | `YYYY-MM-DD` if the text dates the exchange, else `null` |
| `quote` | the exact sentence(s) the numbers come from (shown on the dashboard, so a human can check) |

Mapping: `exchange_event` → `kind='pow'` (counted); `bodies_repatriation` → `kind='bodies'`;
everything else → `kind='other'` (stored, not counted).

**Step 1: failing test** (fake client — the API is never called in tests)
```python
# tests/test_llm.py
import json, unittest
from types import SimpleNamespace as NS
from powx import llm

def reply(obj, stop="end_turn"):
    return NS(stop_reason=stop, model="m", content=[NS(type="text", text=json.dumps(obj))])

class FakeMessages:
    def __init__(self, resp): self.resp, self.calls = resp, []
    def create(self, **kw): self.calls.append(kw); return self.resp

def client(resp): return NS(beta=NS(messages=FakeMessages(resp)))

OK = {"report_type": "exchange_event", "returned_to_ukraine": 84, "returned_to_russia": None,
      "civilians_to_ukraine": None, "exchange_date": "2024-01-03", "quote": "Додому повертаються 84 українці."}

class LlmTest(unittest.TestCase):
    def test_request_shape(self):
        c = client(reply(OK))
        llm.extract(c, "текст", side="ua", published_at="2024-01-03T10:00:00+00:00")
        kw = c.beta.messages.calls[0]
        self.assertEqual(kw["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(kw["output_config"]["effort"], "low")
        self.assertEqual(kw["fallbacks"], "default")
        self.assertIn("server-side-fallback-2026-07-01", kw["betas"])
        self.assertIn("текст", kw["messages"][0]["content"])
        self.assertIn("ua", kw["messages"][0]["content"])

    def test_maps_exchange_event(self):
        r = llm.extract(client(reply(OK)), "t", "ua", "2024-01-03T10:00:00+00:00")
        self.assertEqual((r["kind"], r["n_to_ua"], r["n_to_ru"], r["exchange_date"], r["llm_status"]),
                         ("pow", 84, None, "2024-01-03", "done"))

    def test_cumulative_total_not_counted(self):
        r = llm.extract(client(reply(dict(OK, report_type="cumulative_total", returned_to_ukraine=4000))),
                        "t", "ua", "2024-01-03T10:00:00+00:00")
        self.assertEqual(r["kind"], "other")

    def test_refusal_and_truncation_marked_failed(self):
        for stop in ("refusal", "max_tokens"):
            r = llm.extract(client(reply(OK, stop=stop)), "t", "ua", "2024-01-03T10:00:00+00:00")
            self.assertEqual(r["llm_status"], "failed")

    def test_bad_date_dropped(self):
        r = llm.extract(client(reply(dict(OK, exchange_date="3 Jan"))), "t", "ua", "2024-01-03T10:00:00+00:00")
        self.assertIsNone(r["exchange_date"])
```

**Step 2:** run → FAIL (ImportError).

**Step 3: implementation**
```python
# powx/llm.py
import json, os, re

MODEL = os.environ.get("POWX_MODEL", "claude-opus-5-5")
BETAS = ["server-side-fallback-2026-07-01"]
NULLABLE_INT = {"anyOf": [{"type": "integer"}, {"type": "null"}]}
SCHEMA = {
    "type": "object",
    "properties": {
        "report_type": {"type": "string", "enum": ["exchange_event", "cumulative_total",
                        "negotiation_or_plan", "bodies_repatriation", "other"]},
        "returned_to_ukraine": NULLABLE_INT,
        "returned_to_russia": NULLABLE_INT,
        "civilians_to_ukraine": NULLABLE_INT,
        "exchange_date": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "quote": {"type": "string"},
    },
    "required": ["report_type", "returned_to_ukraine", "returned_to_russia",
                 "civilians_to_ukraine", "exchange_date", "quote"],
    "additionalProperties": False,
}
SYSTEM = """You extract facts about prisoner-of-war exchanges between Russia and Ukraine from \
one post or article (Ukrainian, Russian or English).
Rules:
- report_type=exchange_event only if the text reports a specific exchange or return of living \
prisoners that happened (not plans, negotiations, or running totals since 2022 — those are \
negotiation_or_plan / cumulative_total). Return of bodies of the dead = bodies_repatriation.
- returned_to_ukraine / returned_to_russia: number of living people returned to that side in \
this exchange. Use null when the text does not state it. Never infer one side from the other \
unless the text says the exchange was N for N or "each".
- "Ours", "our defenders", "наших" refer to the publisher's side (given below).
- exchange_date: YYYY-MM-DD only if the text states or clearly implies the date \
("today" = the publication date); otherwise null.
- quote: copy the exact sentence(s) the numbers come from, verbatim; empty string if none."""
KIND = {"exchange_event": "pow", "bodies_repatriation": "bodies"}

def build_params(text, side, published_at):
    return {
        "model": MODEL,
        "max_tokens": 2048,
        "system": SYSTEM,
        "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        "messages": [{"role": "user", "content":
                      f"Publisher side: {side}\nPublished at: {published_at}\n\n<post>\n{text}\n</post>"}],
    }

def parse_message(msg):
    """Map an API message to mention columns. Never raises on model output."""
    failed = {"llm_status": "failed", "llm_model": getattr(msg, "model", None)}
    if msg.stop_reason in ("refusal", "max_tokens"):
        return failed
    try:
        data = json.loads(next(b.text for b in msg.content if b.type == "text"))
    except (StopIteration, json.JSONDecodeError):
        return failed
    date = data.get("exchange_date")
    if not (isinstance(date, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date)):
        date = None
    return {"llm_status": "done", "llm_model": msg.model, "kind": KIND.get(data["report_type"], "other"),
            "report_type": data["report_type"], "n_to_ua": data["returned_to_ukraine"],
            "n_to_ru": data["returned_to_russia"], "n_civilians_to_ua": data["civilians_to_ukraine"],
            "exchange_date": date, "quote": data["quote"]}

def extract(client, text, side, published_at):
    msg = client.beta.messages.create(**build_params(text, side, published_at),
                                      betas=BETAS, fallbacks="default")
    return parse_message(msg)

def make_client():
    import anthropic
    return anthropic.Anthropic()   # default credential chain: ANTHROPIC_API_KEY or `ant auth login`

COLS = ("llm_status", "llm_model", "kind", "report_type", "n_to_ua", "n_to_ru",
        "n_civilians_to_ua", "exchange_date", "quote")

def apply(con, mention_id, result):
    cols = [c for c in COLS if c in result]
    with con:
        con.execute(f"UPDATE mentions SET {', '.join(c + '=?' for c in cols)} WHERE id=?",
                    [result[c] for c in cols] + [mention_id])

def process_pending(con, client, limit=500):
    """Synchronous extraction for incremental updates. API errors leave the row pending."""
    import anthropic
    rows = con.execute("""SELECT m.id, m.text, m.published_at, s.side FROM mentions m
                          JOIN sources s ON s.id=m.source_id WHERE m.llm_status IN ('pending','failed')
                          AND m.llm_attempts < 3 ORDER BY m.published_at LIMIT ?""", (limit,)).fetchall()
    done = 0
    for r in rows:
        with con:
            con.execute("UPDATE mentions SET llm_attempts=llm_attempts+1 WHERE id=?", (r["id"],))
        try:
            apply(con, r["id"], extract(client, r["text"], r["side"], r["published_at"]))
            done += 1
        except anthropic.RateLimitError:
            break                       # stop this round; next update continues
        except (anthropic.APIStatusError, anthropic.APIConnectionError):
            continue                    # stays pending/failed, retried next round
    return done
```
Add `anthropic>=1.0` to `requirements.txt`. Add a test for `process_pending` with the fake
client (two pending rows → both `done`; row with `llm_attempts=3` untouched).

**Step 4:** PASS. **Step 5:** commit `powx: Claude structured extraction (sync path)`.

---

### Task 3b: Batch extraction for the backfill (Message Batches API, 50 % cheaper)

**Files:** Create `powx/llm_batch.py`; Test `tests/test_llm_batch.py`

**Step 1: failing test** — fake `client.messages.batches` with `create/retrieve/results`:
- `submit(con, client)` sends one `Request(custom_id=str(mention_id), params=build_params(...))`
  per pending row (≤ 10 000 per batch), stores the batch id in `llm_batches`, sets those rows to
  `llm_status='batched'`. Assert the custom_ids and the stored batch row.
- `collect(con, client)` for a batch whose `processing_status=="ended"`: `succeeded` results
  → `parse_message` → `apply`; `errored`/`expired`/`canceled` → row back to `pending` (the sync
  path retries it); batch row marked `collected`. A batch still `in_progress` is left alone.

**Step 2:** FAIL. **Step 3: implementation**
```python
# powx/llm_batch.py
from datetime import datetime, timezone
from powx.llm import apply, build_params, parse_message

CHUNK = 10_000

def submit(con, client):
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    rows = con.execute("""SELECT m.id, m.text, m.published_at, s.side FROM mentions m
                          JOIN sources s ON s.id=m.source_id WHERE m.llm_status='pending'
                          ORDER BY m.id LIMIT ?""", (CHUNK,)).fetchall()
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
        for res in client.messages.batches.results(bid):     # any order → key by custom_id
            mid = int(res.custom_id)
            if res.result.type == "succeeded":
                apply(con, mid, parse_message(res.result.message))
            else:
                apply(con, mid, {"llm_status": "pending"})
        with con:
            con.execute("UPDATE llm_batches SET status='collected' WHERE id=?", (bid,))
        collected += 1
    return collected
```
Batch requests carry no `fallbacks` (beta, sync path only); a batch `refusal` comes back as
`failed` from `parse_message` and is retried by the sync path, which has the fallback.
CLI: `python -m powx.llm_batch submit|collect --db powx.db` (repeat `submit` until it prints
`None`; run `collect` every ~10 min until all batches are `collected`).

**Cost gate (manual, before the first full batch):** run the sync path on 200 candidates
(`process_pending(limit=200)`), read the token usage, extrapolate to the pending count, and
show the user the number before submitting. Also eyeball 30 results against their `quote`.

**Step 4:** PASS. **Step 5:** commit `powx: batch extraction for backfill`.

---

### Task 4: HTTP helper + Telegram fetcher

**Files:** Create `powx/http.py`, `powx/fetchers/telegram.py`, `tests/fixtures/tg_page.html`;
Test `tests/test_telegram.py`

**Step 1: fixture + failing test.** The fixture mirrors the real `t.me/s/` markup (verify the
class names against a live page on the first local run; adjust selectors only):
```html
<!-- tests/fixtures/tg_page.html -->
<html><body><section class="tgme_channel_history">
 <div class="tgme_widget_message" data-post="koordshtab/101">
  <div class="tgme_widget_message_text">Відбувся обмін полоненими. Додому повертаються 84 українці.</div>
  <a class="tgme_widget_message_date" href="https://t.me/koordshtab/101"><time datetime="2024-01-03T12:00:00+02:00"></time></a>
 </div>
 <div class="tgme_widget_message" data-post="koordshtab/102">
  <a class="tgme_widget_message_forwarded_from_name" href="https://t.me/V_Zelenskiy_official/9000">Zelensky</a>
  <div class="tgme_widget_message_text">Повертаємо наших!</div>
  <a class="tgme_widget_message_date" href="https://t.me/koordshtab/102"><time datetime="2024-01-03T13:00:00+02:00"></time></a>
 </div>
 <div class="tgme_widget_message" data-post="koordshtab/103"><div class="tgme_widget_message_text">без дати</div></div>
</section></body></html>
```
```python
# tests/test_telegram.py
import pathlib, unittest
from powx.fetchers import telegram

HTML = (pathlib.Path(__file__).parent / "fixtures/tg_page.html").read_text()

def page(ids, date="2024-01-03T10:00:00+00:00"):
    return "".join(f'<div class="tgme_widget_message" data-post="c/{i}"><div class="tgme_widget_message_text">x</div>'
                   f'<a class="tgme_widget_message_date"><time datetime="{date}"></time></a></div>' for i in ids)

class TelegramTest(unittest.TestCase):
    def test_parse_page(self):
        items = telegram.parse_page(HTML)
        self.assertEqual([i.external_id for i in items], ["101", "102"])   # undated skipped
        self.assertEqual(items[0].published_at, "2024-01-03T10:00:00+00:00")  # normalized to UTC
        self.assertEqual(items[1].forwarded_from, "https://t.me/V_Zelenskiy_official/9000")
        self.assertEqual(items[0].url, "https://t.me/koordshtab/101")

    def test_iter_older_paginates_with_before(self):
        pages = {"https://t.me/s/c": page([30, 31]), "https://t.me/s/c?before=30": page([10, 11]),
                 "https://t.me/s/c?before=10": ""}
        got = [[i.external_id for i in p] for p in telegram.iter_older("c", None, pages.__getitem__, "2022-02-24")]
        self.assertEqual(got, [["30", "31"], ["10", "11"]])

    def test_iter_older_stops_at_start_date(self):
        old = page([5], date="2021-01-01T00:00:00+00:00")
        pages = {"https://t.me/s/c": old}
        self.assertEqual(len(list(telegram.iter_older("c", None, pages.__getitem__, "2022-02-24"))), 1)

    def test_iter_newer_stops_at_cursor(self):
        pages = {"https://t.me/s/c": page([50, 51]), "https://t.me/s/c?before=50": page([48, 49])}
        got = [[i.external_id for i in p] for p in telegram.iter_newer("c", "48", pages.__getitem__)]
        self.assertEqual(got, [["50", "51"], ["49"]])
```

**Step 2:** run → FAIL (ImportError).

**Step 3: implementation**
```python
# powx/http.py
import time, urllib.error, urllib.request

UA = "Mozilla/5.0 (compatible; powx/0.1; POW exchange tracker)"

def get(url, *, retries=4, throttle=1.5, timeout=30) -> str:
    """GET with polite throttle and exponential backoff on 429/5xx/network errors."""
    delay = 2
    for attempt in range(retries + 1):
        time.sleep(throttle)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode(r.headers.get_content_charset() or "utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == retries:
                raise
        except urllib.error.URLError:
            if attempt == retries:
                raise
        time.sleep(delay); delay *= 2
```
```python
# powx/fetchers/telegram.py
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from powx.models import Item

def to_utc(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(timezone.utc).isoformat()

def parse_page(html: str) -> list[Item]:
    out = []
    for div in BeautifulSoup(html, "lxml").select("div.tgme_widget_message[data-post]"):
        channel, _, pid = div["data-post"].partition("/")
        tm = div.select_one(".tgme_widget_message_date time[datetime]")
        if not tm or not pid.isdigit():
            continue
        txt = div.select_one(".tgme_widget_message_text")
        fw = div.select_one("a.tgme_widget_message_forwarded_from_name[href]")
        out.append(Item(external_id=pid, url=f"https://t.me/{channel}/{pid}",
                        published_at=to_utc(tm["datetime"]),
                        text=txt.get_text("\n", strip=True) if txt else "",
                        forwarded_from=fw["href"] if fw else None))
    return sorted(out, key=lambda i: int(i.external_id))

def page_url(channel, before=None):
    return f"https://t.me/s/{channel}" + (f"?before={before}" if before else "")

def iter_older(channel, before, http, stop_date):
    """Yield pages walking back in time until stop_date or channel start."""
    while True:
        items = parse_page(http(page_url(channel, before)))
        if not items:
            return
        yield items
        oldest = items[0]
        if oldest.published_at < stop_date or (before and int(oldest.external_id) >= int(before)):
            return
        before = oldest.external_id

def iter_newer(channel, after_id, http):
    """Yield pages of posts newer than after_id (None → only the newest page)."""
    before = None
    while True:
        items = parse_page(http(page_url(channel, before)))
        new = [i for i in items if after_id is None or int(i.external_id) > int(after_id)]
        if new:
            yield new
        if not items or after_id is None or len(new) < len(items):
            return
        before = items[0].external_id
```

**Step 4:** PASS. **Step 5:** commit `powx: telegram public-preview fetcher with pagination`.

---

### Task 5: RSS/Atom fetcher

**Files:** Create `powx/fetchers/rss.py`; Test `tests/test_rss.py`

**Step 1: failing test**
```python
# tests/test_rss.py
import unittest
from powx.fetchers.rss import parse_feed

RSS = """<rss><channel><item><title>Обмін полоненими</title><link>https://ex.ua/a</link>
<guid>a-1</guid><pubDate>Wed, 03 Jan 2024 12:00:00 +0200</pubDate>
<description>&lt;p&gt;Додому повертаються 230 українців&lt;/p&gt;</description></item></channel></rss>"""
ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>urn:b</id><title>Swap</title>
<link href="https://ex.com/b"/><updated>2024-01-03T10:00:00Z</updated><summary>POW swap</summary></entry></feed>"""

class RssTest(unittest.TestCase):
    def test_rss(self):
        [i] = parse_feed(RSS)
        self.assertEqual((i.external_id, i.url, i.published_at), ("a-1", "https://ex.ua/a", "2024-01-03T10:00:00+00:00"))
        self.assertEqual(i.text, "Обмін полоненими\nДодому повертаються 230 українців")

    def test_atom(self):
        [i] = parse_feed(ATOM)
        self.assertEqual((i.external_id, i.url, i.published_at), ("urn:b", "https://ex.com/b", "2024-01-03T10:00:00+00:00"))
```

**Step 2:** FAIL. **Step 3: implementation**
```python
# powx/fetchers/rss.py
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
from powx.fetchers.telegram import to_utc
from powx.models import Item

A = "{http://www.w3.org/2005/Atom}"

def _plain(html):
    return BeautifulSoup(html or "", "lxml").get_text(" ", strip=True)

def parse_feed(xml: str) -> list[Item]:
    root = ET.fromstring(xml)
    out = []
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        date = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc).isoformat()
        text = "\n".join(filter(None, [_plain(it.findtext("title")), _plain(it.findtext("description"))]))
        out.append(Item((it.findtext("guid") or link).strip(), link, date, text))
    for e in root.iter(A + "entry"):
        link_el = e.find(A + "link")
        date = (e.findtext(A + "published") or e.findtext(A + "updated")).replace("Z", "+00:00")
        text = "\n".join(filter(None, [_plain(e.findtext(A + "title")), _plain(e.findtext(A + "summary"))]))
        out.append(Item(e.findtext(A + "id"), link_el.get("href") if link_el is not None else "", to_utc(date), text))
    return out

def fetch(url, http):
    return parse_feed(http(url))
```
RSS only exposes recent items — it is incremental-only by nature (README says so).

**Step 4:** PASS. **Step 5:** commit `powx: RSS/Atom fetcher`.

---

### Task 6: Wikipedia seed fetcher

**Files:** Create `powx/fetchers/wikipedia.py`; Test `tests/test_wikipedia.py`

**Step 1: failing test**
```python
# tests/test_wikipedia.py
import json, unittest
from powx.fetchers import wikipedia

TABLE = """<table class="wikitable"><tr><th>Date</th><th>Ukrainians returned</th><th>Russians returned</th></tr>
<tr><td>3 January 2024</td><td>230<sup>[12]</sup></td><td>248</td></tr>
<tr><td>May 23, 2025</td><td>1,000</td><td>1,000</td></tr>
<tr><td>unknown</td><td>5</td><td>5</td></tr></table>"""

class WikiTest(unittest.TestCase):
    def test_parse_rows(self):
        rows = wikipedia.parse_exchanges(TABLE, "https://en.wikipedia.org/wiki/X")
        self.assertEqual([(r.published_at[:10], r.n_to_ua, r.n_to_ru, r.kind) for r in rows],
                         [("2024-01-03", 230, 248, "pow"), ("2025-05-23", 1000, 1000, "pow")])

    def test_fetch_uses_parse_api(self):
        seen = []
        def http(url): seen.append(url); return json.dumps({"parse": {"text": TABLE}})
        self.assertEqual(len(wikipedia.fetch("Some Title", http)), 2)
        self.assertIn("action=parse", seen[0]); self.assertIn("Some_Title", seen[0])
```

**Step 2:** FAIL. **Step 3: implementation**
```python
# powx/fetchers/wikipedia.py
import json, re
from datetime import datetime
from urllib.parse import quote
from bs4 import BeautifulSoup
from powx.models import Item

API = "https://en.wikipedia.org/w/api.php"
FORMATS = ("%d %B %Y", "%B %d, %Y", "%Y-%m-%d", "%d %b %Y", "%b %d, %Y")

def _date(s):
    s = re.sub(r"\[[^\]]*\]", "", s).strip()
    for f in FORMATS:
        try: return datetime.strptime(s, f).date().isoformat()
        except ValueError: pass
    return None

def _num(s):
    m = re.search(r"\d[\d,\s]*", re.sub(r"\[[^\]]*\]", "", s))
    return int(re.sub(r"\D", "", m[0])) if m else None

def _col(headers, *needles):
    return next((i for i, h in enumerate(headers) if any(n in h for n in needles)), None)

def parse_exchanges(html, page_url):
    out = []
    for table in BeautifulSoup(html, "lxml").select("table.wikitable"):
        rows = table.select("tr")
        if not rows: continue
        headers = [c.get_text(" ", strip=True).lower() for c in rows[0].find_all(["th", "td"])]
        d, ua, ru = _col(headers, "date"), _col(headers, "ukrain"), _col(headers, "russia")
        if d is None or (ua is None and ru is None): continue
        for tr in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) <= max(i for i in (d, ua, ru) if i is not None): continue
            date = _date(cells[d])
            if not date: continue
            n_ua = _num(cells[ua]) if ua is not None else None
            n_ru = _num(cells[ru]) if ru is not None else None
            out.append(Item(f"wiki:{date}:{n_ua}:{n_ru}", page_url, f"{date}T12:00:00+00:00",
                            " | ".join(cells), kind="pow", n_to_ua=n_ua, n_to_ru=n_ru))
    return out

def fetch(title, http):
    t = quote(title.replace(" ", "_"))
    data = json.loads(http(f"{API}?action=parse&page={t}&prop=text&formatversion=2&format=json&redirects=1"))
    return parse_exchanges(data["parse"]["text"], f"https://en.wikipedia.org/wiki/{t}")
```
Known limit: `rowspan` cells shift columns — rows that don't parse are skipped, not guessed.
The exact article title goes in `sources.json` and is verified on the first live run
(`action=query&list=search` by hand); a wrong title logs an error in `sources.last_error`.

**Step 4:** PASS. **Step 5:** commit `powx: wikipedia exchange-table seed`.

---

### Task 7: Clustering — events, consensus numbers, primary source (pure)

**Files:** Create `powx/cluster.py`; Test `tests/test_cluster.py`

Rules (from design): a numbered POW mention joins the closest event whose anchor is ≤ 36 h away
and whose consensus numbers are within ±2 on every side both know; otherwise founds a new
event. Number-less mentions only attach (never found an event). Consensus per side: mode of
tier-1 sources of that side → else tier ≤ 2 → else all. Primary = earliest non-copy mention of
the best tier (1 → 2 → 3); a copy = forwarded or same `text_hash` seen earlier. If the
primary is tier 3 (Wikipedia only), the event is flagged `no primary source found` in the UI.

**Step 1: failing test**
```python
# tests/test_cluster.py
import unittest
from datetime import datetime, timedelta
from powx.cluster import M, cluster

T0 = datetime(2024, 1, 3, 10)
def m(id, src, tier, side, h, ua=None, ru=None, copy=False):
    return M(id=id, source_id=src, tier=tier, side=side, published_at=T0 + timedelta(hours=h),
             n_to_ua=ua, n_to_ru=ru, is_copy=copy, url=f"u{id}")

class ClusterTest(unittest.TestCase):
    def test_two_sides_one_exchange(self):
        [ev] = cluster([m(1, "koord", 1, "ua", 0, ua=230), m(2, "mod", 1, "ru", 1, ua=230, ru=248),
                        m(3, "wiki", 3, "neutral", 2, ua=230, ru=248)])
        self.assertEqual((ev.n_to_ua, ev.n_to_ru, ev.primary.id, ev.source_count), (230, 248, 1, 3))

    def test_different_numbers_same_day_are_two_events(self):
        self.assertEqual(len(cluster([m(1, "a", 1, "ua", 0, ua=100), m(2, "b", 1, "ua", 3, ua=40)])), 2)

    def test_far_apart_are_two_events(self):
        self.assertEqual(len(cluster([m(1, "a", 1, "ua", 0, ua=100), m(2, "a", 1, "ua", 72, ua=100)])), 2)

    def test_numberless_mention_attaches_but_never_founds(self):
        evs = cluster([m(1, "a", 1, "ua", 0, ua=50), m(2, "b", 2, "ua", 5), m(3, "b", 2, "ua", 200)])
        self.assertEqual([[x.id for x in e.mentions] for e in evs], [[1, 2]])

    def test_primary_skips_copies_and_prefers_tier1(self):
        [ev] = cluster([m(1, "news", 2, "ua", 0, ua=90), m(2, "koord", 1, "ua", 1, ua=90, copy=True),
                        m(3, "zel", 1, "ua", 2, ua=90)])
        self.assertEqual(ev.primary.id, 3)

    def test_tolerance_absorbs_updates(self):
        [ev] = cluster([m(1, "a", 1, "ua", 0, ua=150), m(2, "b", 1, "ua", 2, ua=151), m(3, "c", 2, "ua", 3, ua=151)])
        self.assertEqual(ev.n_to_ua, 151)
```

**Step 2:** FAIL. **Step 3: implementation**
```python
# powx/cluster.py
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

WINDOW = timedelta(hours=36)
TOL = 2
SIDES = (("n_to_ua", "ua"), ("n_to_ru", "ru"))

@dataclass
class M:
    id: int; source_id: str; tier: int; side: str; published_at: datetime
    n_to_ua: int | None; n_to_ru: int | None; is_copy: bool; url: str

@dataclass
class Event:
    anchor: datetime
    mentions: list = field(default_factory=list)
    n_to_ua: int | None = None; n_to_ru: int | None = None
    primary: M | None = None; source_count: int = 0

def consensus(ms, attr, side):
    pools = ([x for x in ms if x.tier == 1 and x.side == side], [x for x in ms if x.tier <= 2], ms)
    for pool in pools:
        vals = [getattr(x, attr) for x in pool if getattr(x, attr) is not None]
        if vals:
            top = Counter(vals).most_common()
            best = max(c for _, c in top)
            return max(v for v, c in top if c == best)   # tie → larger (later corrections add people)
    return None

def _compatible(ev, m):
    for attr, side in SIDES:
        v, c = getattr(m, attr), consensus(ev.mentions, attr, side)
        if v is not None and c is not None and abs(v - c) > TOL:
            return False
    return True

def _has_numbers(m):
    return m.n_to_ua is not None or m.n_to_ru is not None

def primary(ms):
    originals = [x for x in ms if not x.is_copy] or ms
    for tier in (1, 2, 3):
        cand = [x for x in originals if x.tier == tier]
        if cand:
            return min(cand, key=lambda x: (x.published_at, x.id))
    return min(originals, key=lambda x: (x.published_at, x.id))

def cluster(mentions):
    events = []
    for m in sorted(mentions, key=lambda x: (x.published_at, x.id)):
        cands = [(abs(m.published_at - e.anchor), e) for e in events
                 if abs(m.published_at - e.anchor) <= WINDOW and _compatible(e, m)]
        if cands:
            min(cands, key=lambda c: c[0])[1].mentions.append(m)
        elif _has_numbers(m):
            events.append(Event(anchor=m.published_at, mentions=[m]))
    for e in events:
        e.n_to_ua = consensus(e.mentions, "n_to_ua", "ua")
        e.n_to_ru = consensus(e.mentions, "n_to_ru", "ru")
        e.primary = primary(e.mentions)
        e.source_count = len({x.source_id for x in e.mentions if not x.is_copy})
    return events
```
(`test_two_sides_one_exchange`: n_to_ua from tier-1 UA pool = 230; n_to_ru from tier-1 RU
pool = 248.)

**Step 4:** PASS. **Step 5:** commit `powx: cluster mentions into exchange events`.

---

### Task 8: Persist clustering (`recluster`) with manual overrides

**Files:** Modify `powx/cluster.py`; Test `tests/test_recluster.py`

**Step 1: failing test**
```python
# tests/test_recluster.py
import unittest
from powx import db
from powx.cluster import recluster

class ReclusterTest(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(":memory:")
        for s in [("koord", "ua", 1), ("mod", "ru", 1), ("echo", "ua", 2)]:
            db.upsert_source(self.con, {"id": s[0], "kind": "telegram", "handle": s[0], "side": s[1], "tier": s[2]})
        rows = [("koord", "1", "2024-01-03T10:00:00+00:00", "h1", None, 230, None),
                ("mod", "1", "2024-01-03T11:00:00+00:00", "h2", None, None, 248),
                ("echo", "1", "2024-01-03T12:00:00+00:00", "h1", None, 230, None),   # same text → copy
                ("koord", "2", "2024-02-01T10:00:00+00:00", "h3", None, 100, None)]
        for src, ext, at, h, fw, ua, ru in rows:
            db.insert_mention(self.con, dict(source_id=src, external_id=ext, url=f"https://t.me/{src}/{ext}",
                published_at=at, text="x", text_hash=h, forwarded_from=fw, kind="pow", n_to_ua=ua, n_to_ru=ru))

    def q(self, sql): return [tuple(r) for r in self.con.execute(sql)]

    def test_events_written_and_idempotent(self):
        recluster(self.con); recluster(self.con)
        self.assertEqual(self.q("SELECT date, n_to_ua, n_to_ru, mention_count, source_count, primary_url FROM events ORDER BY date"),
                         [("2024-01-03", 230, 248, 3, 2, "https://t.me/koord/1"), ("2024-02-01", 100, None, 1, 1, "https://t.me/koord/2")])

    def test_manual_override_survives(self):
        recluster(self.con)
        self.con.execute("UPDATE events SET n_to_ua=231, manual_override=1 WHERE date='2024-01-03'")
        recluster(self.con)
        self.assertEqual(self.q("SELECT n_to_ua FROM events WHERE date='2024-01-03'"), [(231,)])
        self.assertEqual(self.q("SELECT count(*) FROM events"), [(2,)])
```

**Step 2:** FAIL (ImportError `recluster`). **Step 3: implementation** (append)
```python
def _dt(s):
    return datetime.fromisoformat(s)

def recluster(con):
    """Recompute all non-overridden events from mentions. Idempotent."""
    with con:
        con.execute("""UPDATE mentions SET event_id=NULL WHERE event_id IN
                       (SELECT id FROM events WHERE manual_override=0)""")
        con.execute("DELETE FROM events WHERE manual_override=0")
        # effective time: the exchange date the LLM read from the text (retrospective posts),
        # else the publication time
        rows = con.execute("""SELECT m.*, s.tier, s.side,
                                coalesce(m.exchange_date || 'T12:00:00+00:00', m.published_at) AS t
                              FROM mentions m JOIN sources s ON s.id=m.source_id
                              WHERE m.kind='pow' AND m.event_id IS NULL
                              ORDER BY t, m.id""").fetchall()
        seen, ms = set(), []
        for r in rows:
            ms.append(M(r["id"], r["source_id"], r["tier"], r["side"], _dt(r["t"]),
                        r["n_to_ua"], r["n_to_ru"], r["forwarded_from"] is not None or r["text_hash"] in seen, r["url"]))
            seen.add(r["text_hash"])
        for e in cluster(ms):
            p = e.primary
            url = p.url
            if p.is_copy:   # only copies exist → point at the original post
                url = con.execute("SELECT forwarded_from FROM mentions WHERE id=?", (p.id,)).fetchone()[0] or p.url
            cur = con.execute("""INSERT INTO events(date, n_to_ua, n_to_ru, primary_mention_id, primary_url,
                                 mention_count, source_count) VALUES(?,?,?,?,?,?,?)""",
                              (p.published_at.date().isoformat(), e.n_to_ua, e.n_to_ru, p.id, url,
                               len(e.mentions), e.source_count))
            con.executemany("UPDATE mentions SET event_id=? WHERE id=?",
                            [(cur.lastrowid, x.id) for x in e.mentions])
```
Note: event ids are not stable across reclusters (UI links by date); `manual_override=1`
events and their mentions are frozen.

**Step 4:** PASS. **Step 5:** commit `powx: persist clustering with manual overrides`.

---

### Task 9: Crawler (backfill / update) + sources.json

**Files:** Create `powx/crawl.py`, `pow-exchanges/sources.json`; Test `tests/test_crawl.py`

**Step 1: failing test**
```python
# tests/test_crawl.py
import unittest
from powx import crawl, db

def tg(ids, text="Обмін полоненими: додому повертаються 84 українці", date="2024-01-03T10:00:00+00:00"):
    return "".join(f'<div class="tgme_widget_message" data-post="koord/{i}"><div class="tgme_widget_message_text">{text}</div>'
                   f'<a class="tgme_widget_message_date"><time datetime="{date}"></time></a></div>' for i in ids)

SOURCES = [{"id": "koord", "kind": "telegram", "handle": "koord", "side": "ua", "tier": 1}]

class CrawlTest(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(":memory:")

    @staticmethod
    def fake_extractor(con):   # stands in for the LLM step
        con.execute("""UPDATE mentions SET kind='pow', n_to_ua=84, llm_status='done'
                       WHERE llm_status='pending'""")
        con.commit()

    def test_backfill_then_update(self):
        pages = {"https://t.me/s/koord": tg([20, 21]), "https://t.me/s/koord?before=20": tg([10]),
                 "https://t.me/s/koord?before=10": ""}
        crawl.run(self.con, SOURCES, "backfill", http=pages.__getitem__)
        self.assertEqual(self.con.execute("SELECT count(*) FROM mentions WHERE llm_status='pending'").fetchone()[0], 3)
        self.fake_extractor(self.con); crawl.run(self.con, [], "update", extractor=None)
        src = db.get_source(self.con, "koord")
        self.assertEqual((src["cursor_newest"], src["cursor_oldest"], src["backfill_done"]), ("21", "10", 1))
        self.assertEqual(self.con.execute("SELECT count(*) FROM mentions WHERE kind='pow' AND n_to_ua=84").fetchone()[0], 3)
        self.assertEqual(self.con.execute("SELECT count(*) FROM events").fetchone()[0], 1)

        pages["https://t.me/s/koord"] = tg([21, 22])
        stats = crawl.run(self.con, SOURCES, "update", http=pages.__getitem__, extractor=self.fake_extractor)
        self.assertEqual(stats["koord"], 1)
        self.assertEqual(self.con.execute("SELECT count(*) FROM mentions WHERE llm_status='pending'").fetchone()[0], 0)

    def test_non_candidates_skip_llm(self):
        pages = {"https://t.me/s/koord": tg([5], text="Обстріл Харкова"), "https://t.me/s/koord?before=5": ""}
        crawl.run(self.con, SOURCES, "backfill", http=pages.__getitem__)
        self.assertEqual(tuple(self.con.execute("SELECT kind, llm_status FROM mentions").fetchone()), ("other", "skipped"))
        self.assertEqual(db.get_source(self.con, "koord")["cursor_newest"], "22")

    def test_source_error_is_recorded_not_raised(self):
        def boom(url): raise OSError("blocked")
        crawl.run(self.con, SOURCES, "update", http=boom)
        self.assertIn("blocked", db.get_source(self.con, "koord")["last_error"])
```

**Step 2:** FAIL. **Step 3: implementation**
```python
# powx/crawl.py
import argparse, json, logging, pathlib
from datetime import datetime, timezone
from powx import db, http as http_mod
from powx.cluster import recluster
from powx import llm
from powx.prefilter import is_candidate, text_hash
from powx.fetchers import rss, telegram, wikipedia

START = "2022-02-24T00:00:00+00:00"
log = logging.getLogger("powx.crawl")

def ingest(con, src, items):
    """Store raw items. Structured rows (wikipedia) are final; candidates wait for the LLM."""
    new = 0
    for it in items:
        if it.kind:                          # structured source: numbers already known
            kind, status = it.kind, "skipped"
        elif is_candidate(it.text):
            kind, status = "candidate", "pending"
        else:
            kind, status = "other", "skipped"
        new += db.insert_mention(con, dict(
            source_id=src["id"], external_id=it.external_id, url=it.url, published_at=it.published_at,
            text=it.text, text_hash=text_hash(it.text), forwarded_from=it.forwarded_from,
            kind=kind, n_to_ua=it.n_to_ua, n_to_ru=it.n_to_ru, llm_status=status))
    return new

def sync_extractor(con):
    llm.process_pending(con, llm.make_client())

def _telegram(con, src, mode, http):
    row, new = db.get_source(con, src["id"]), 0
    if mode == "backfill" and not row["backfill_done"]:
        for page in telegram.iter_older(src["handle"], row["cursor_oldest"], http, START):
            new += ingest(con, src, page)
            cur = db.get_source(con, src["id"])
            newest = max(int(cur["cursor_newest"] or 0), int(page[-1].external_id))
            db.set_cursor(con, src["id"], cursor_oldest=page[0].external_id, cursor_newest=str(newest))
        db.set_cursor(con, src["id"], backfill_done=1)
    else:
        for page in telegram.iter_newer(src["handle"], row["cursor_newest"], http):
            new += ingest(con, src, page)
            cur = db.get_source(con, src["id"])
            newest = max(int(cur["cursor_newest"] or 0), int(page[-1].external_id))
            db.set_cursor(con, src["id"], cursor_newest=str(newest))
    return new

def crawl_source(con, src, mode, http):
    if src["kind"] == "telegram":
        return _telegram(con, src, mode, http)
    if src["kind"] == "rss":
        return ingest(con, src, rss.fetch(src["handle"], http))
    if src["kind"] == "wikipedia":
        return ingest(con, src, wikipedia.fetch(src["handle"], http))
    raise ValueError(f"unknown source kind {src['kind']}")

def run(con, sources, mode, http=http_mod.get, extractor=sync_extractor):
    """Crawl, then extract. Backfill leaves candidates pending for the batch path (llm_batch)."""
    stats = {}
    for src in sources:
        db.upsert_source(con, src)
        now = datetime.now(timezone.utc).isoformat()
        try:
            stats[src["id"]] = crawl_source(con, src, mode, http)
            db.set_cursor(con, src["id"], last_error=None, last_run_at=now)
        except Exception as e:  # one broken source must not stop the others
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
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO)
    print(run(db.connect(a.db), load_sources(a.sources), a.mode))

if __name__ == "__main__":
    main()
```
```json
// sources.json  (handles verified on first live run; unresolved ones show last_error — fix, don't guess)
{"sources": [
  {"id": "koordshtab", "kind": "telegram", "handle": "koordshtab", "side": "ua", "tier": 1},
  {"id": "zelenskiy", "kind": "telegram", "handle": "V_Zelenskiy_official", "side": "ua", "tier": 1},
  {"id": "lubinets", "kind": "telegram", "handle": "dmytro_lubinets", "side": "ua", "tier": 1},
  {"id": "gur", "kind": "telegram", "handle": "DIUkraine", "side": "ua", "tier": 1},
  {"id": "mod_russia", "kind": "telegram", "handle": "mod_russia", "side": "ru", "tier": 1},
  {"id": "moskalkova", "kind": "telegram", "handle": "moskalkova_tatiana", "side": "ru", "tier": 1},
  {"id": "pravda_ua", "kind": "rss", "handle": "https://www.pravda.com.ua/rss/", "side": "ua", "tier": 2},
  {"id": "tass", "kind": "rss", "handle": "https://tass.ru/rss/v2.xml", "side": "ru", "tier": 2},
  {"id": "wikipedia", "kind": "wikipedia", "handle": "Prisoner exchanges in the Russo-Ukrainian war", "side": "neutral", "tier": 3}
]}
```
(Strip the `//` comment line from the real file — JSON has no comments; put the note in README.)

**Step 4:** PASS. **Step 5:** commit `powx: resumable backfill and incremental crawler`.

---

### Task 10: JSON API + server with background updater

**Files:** Create `powx/server.py`; Test `tests/test_server.py`

**Step 1: failing test**
```python
# tests/test_server.py
import json, tempfile, threading, unittest, urllib.request, os
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
                published_at=at, text="x" + ext, text_hash=ext, forwarded_from=None, kind="pow", n_to_ua=ua, n_to_ru=None))
        recluster(con)
        cls.httpd = server.make_server(cls.path, port=0)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls): cls.httpd.shutdown()

    def get(self, p): return json.load(urllib.request.urlopen(self.base + p))

    def test_stats(self):
        self.assertEqual(self.get("/api/stats"), {"exchanges": 2, "to_ua": 330, "to_ru": 0,
                         "last_date": "2024-02-01", "mentions": 2, "sources": 1, "pending_llm": 0})

    def test_monthly_events_mentions(self):
        self.assertEqual([r["month"] for r in self.get("/api/monthly")], ["2024-01", "2024-02"])
        ev = self.get("/api/events")[0]
        self.assertEqual((ev["date"], ev["primary_url"]), ("2024-02-01", "https://t.me/koord/2"))
        self.assertEqual(len(self.get(f"/api/events/{ev['id']}/mentions")), 1)

    def test_index_and_404(self):
        self.assertIn(b"<html", urllib.request.urlopen(self.base + "/").read())
        with self.assertRaises(urllib.error.HTTPError): urllib.request.urlopen(self.base + "/nope")
```

**Step 2:** FAIL. **Step 3: implementation**
```python
# powx/server.py
import argparse, json, logging, pathlib, re, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from powx import crawl, db

STATIC = pathlib.Path(__file__).parent / "static"
log = logging.getLogger("powx.server")

QUERIES = {
  "/api/stats": ("one", """SELECT (SELECT count(*) FROM events) exchanges,
      (SELECT coalesce(sum(n_to_ua),0) FROM events) to_ua, (SELECT coalesce(sum(n_to_ru),0) FROM events) to_ru,
      (SELECT max(date) FROM events) last_date, (SELECT count(*) FROM mentions WHERE kind='pow') mentions,
      (SELECT count(*) FROM sources) sources,
      (SELECT count(*) FROM mentions WHERE llm_status IN ('pending','batched')) pending_llm"""),
  "/api/monthly": ("all", """SELECT substr(date,1,7) month, count(*) exchanges,
      coalesce(sum(n_to_ua),0) to_ua, coalesce(sum(n_to_ru),0) to_ru FROM events GROUP BY month ORDER BY month"""),
  "/api/events": ("all", """SELECT e.*, s.id source_id, s.tier primary_tier FROM events e
      LEFT JOIN mentions m ON m.id=e.primary_mention_id LEFT JOIN sources s ON s.id=m.source_id
      ORDER BY e.date DESC, e.id DESC"""),
  "/api/sources": ("all", """SELECT s.*, (SELECT count(*) FROM mentions m WHERE m.source_id=s.id) mentions
      FROM sources s ORDER BY tier, id"""),
}
MENTIONS = re.compile(r"^/api/events/(\d+)/mentions$")

def make_server(db_path, host="127.0.0.1", port=8000):
    class H(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code); self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

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
                    rows = con.execute("""SELECT m.id, m.source_id, s.tier, m.url, m.published_at, m.text,
                        m.n_to_ua, m.n_to_ru, m.forwarded_from, m.quote, m.report_type, m.llm_model
                        FROM mentions m JOIN sources s ON s.id=m.source_id
                        WHERE m.event_id=? ORDER BY m.published_at""", (int(m[1]),)).fetchall()
                    return self._send(200, [dict(r) for r in rows])
                self._send(404, {"error": "not found"})
            finally:
                con.close()

        def log_message(self, fmt, *args): log.debug(fmt, *args)
    return ThreadingHTTPServer((host, port), H)

def start_updater(db_path, sources_path, interval):
    def loop():
        while True:
            try:
                con = db.connect(db_path)
                log.info("update: %s", crawl.run(con, crawl.load_sources(sources_path), "update"))
                con.close()
            except Exception:
                log.exception("update failed")
            time.sleep(interval)
    threading.Thread(target=loop, daemon=True, name="updater").start()

def main():
    p = argparse.ArgumentParser(prog="powx.server")
    p.add_argument("--db", default="powx.db"); p.add_argument("--sources", default="sources.json")
    p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=8000)
    p.add_argument("--interval", type=int, default=1800, help="seconds between updates; 0 = off")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO)
    db.connect(a.db).close()
    if a.interval:
        start_updater(a.db, a.sources, a.interval)
    srv = make_server(a.db, a.host, a.port)
    log.info("serving on http://%s:%s", a.host, srv.server_address[1])
    srv.serve_forever()

if __name__ == "__main__":
    main()
```
Create a minimal `powx/static/index.html` (`<!doctype html><html><body>…</body></html>`) so
the index test passes; Task 11 fills it.

**Step 4:** PASS. **Step 5:** commit `powx: JSON API server with background updater`.

---

### Task 11: Dashboard page

**Files:** Modify `powx/static/index.html` (no new test file — verified by render in Task 12)

**Step 1: dataviz prep (required before chart code).**
- Form: headline counts → **stat tiles** (exchanges, returned to Ukraine, returned to Russia,
  last exchange date); change over time → **grouped bar chart by month**, 2 series; detail →
  **table** of events.
- Colors: reference palette slots 1–2. Light `--series-ua:#2a78d6` `--series-ru:#eb6834`
  on `--surface-1:#fcfcfb`; dark `#3987e5` / `#d95926` on `#1a1a19`.
- Run the validator (from the dataviz skill dir) and fix anything that FAILs:
  `node scripts/validate_palette.js "#2a78d6,#eb6834" --mode light` and
  `node scripts/validate_palette.js "#3987e5,#d95926" --mode dark`

**Step 2: build the page.** Single self-contained file, no external JS. Requirements:
- `:root` tokens (surface, text-primary `#0b0b0b`/`#f0efec`, text-secondary `#52514e`/`#c3c2b7`,
  grid, series-ua, series-ru), dark mode under
  `@media (prefers-color-scheme: dark) { :root:where(:not([data-theme="light"])) {…} }` and
  `:root[data-theme="dark"]`; explicit `body` background.
- Header row of 4 stat tiles; numbers formatted with `Intl.NumberFormat("uk-UA")`.
  Text in text tokens, never series colors.
- SVG chart rendered by JS from `/api/monthly`: one y-axis, recessive grid, bars ≤ 12px wide,
  4px rounded top ends anchored to baseline, 2px gap between the pair, legend above
  ("Returned to Ukraine" / "Returned to Russia" with swatches), hover tooltip per month
  (month, both counts, number of exchanges), hit target = full month column. A "Table"
  toggle shows the same data as a `<table>`.
- Events table from `/api/events`: date (DD.MM.YYYY), to UA, to RU, primary source (link,
  source id; tier-3 primary shows badge "⚠ no primary source found"), mentions count;
  click a row → fetch `/api/events/<id>/mentions` and expand inline list (time, source,
  numbers, link, the LLM's verbatim `quote` highlighted, first 200 chars of text).
- Footer line: pending LLM extractions count (add `pending_llm` to `/api/stats`).
- Footer: last update from `/api/sources` (max `last_run_at`) + list of sources with
  `last_error` shown as "⚠ <source>: <error>".
- Phone width: 16px gutters, tiles wrap 2×2, table scrolls horizontally inside its own
  container (no page scroll).

**Step 3:** `python -m unittest -v` still PASS. **Step 4:** commit `powx: dashboard page`.

---

### Task 12: Docs, Docker, end-to-end smoke

**Files:** Create `pow-exchanges/README.md`, `pow-exchanges/Dockerfile`,
`tests/fixtures/demo_seed.py` (writes ~6 clearly fake demo mentions — source id `demo`,
text "DEMO" — into a DB path given as argv[1]; used only for screenshots, the DB lives in the
session scratchpad and is never committed)

**Step 1: README** — what it does; quick start
(`pip install -r requirements.txt`; `ant auth login` or `ANTHROPIC_API_KEY`; optional
`POWX_MODEL=claude-haiku-5-5` for the cheap run; `python -m powx.crawl backfill` →
cost gate on 200 samples → `python -m powx.llm_batch submit` (repeat) → `collect` until done →
`python -m powx.server`); how the LLM is used (prefilter → structured extraction, quote kept
for audit, retrospective/cumulative posts not counted);
how dedup/primary-source rules work (copy the rules block from Task 7); source tiers and how
to add a source to `sources.json`; first-live-run checklist (verify tg selectors, channel
handles, Wikipedia title; check `/api/sources` for `last_error`); manual override SQL example
(`UPDATE events SET n_to_ua=…, manual_override=1 WHERE id=…`); limits (RSS has no history;
t.me preview may rate-limit → throttle; numbers are regex-extracted, review outliers).

**Step 2: Dockerfile**
```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
VOLUME /data
EXPOSE 8000
CMD ["python", "-m", "powx.server", "--db", "/data/powx.db", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 3: end-to-end smoke (offline).**
1. `python -m unittest -v` → all PASS (paste the summary line in the final report).
2. Seed a scratch DB in the session scratchpad with the demo script, start
   `python -m powx.server --db <scratch>/demo.db --interval 0 --port 8765` in background.
3. `curl -s localhost:8765/api/stats` → valid JSON with non-zero counts.
4. Playwright screenshots of `/` at 1280px and 390px, light and dark
   (`colorScheme: 'dark'`); look at them: no label collisions, tooltips work on hover,
   no horizontal page scroll. Fix and re-shoot until clean.
5. Stop the server.

**Step 4:** commit `powx: README, Dockerfile, smoke-tested dashboard`, then
`git push -u origin claude/ecstatic-bell-yeogs6` (retry on network error 2/4/8/16 s).

---

## Verification summary
- Unit tests cover: DB idempotency, keyword prefilter, LLM request shape / response mapping /
  refusal + truncation handling / retry accounting (fake client), batch submit + collect (fake
  client), tg-preview
  parsing + both pagination directions, RSS/Atom, Wikipedia tables, clustering (same exchange
  from two sides → 1 event; two exchanges in a day → 2; copies never primary; tier preference;
  ±2 tolerance), recluster idempotency + manual override, crawler cursors/resume/error
  isolation, API endpoints.
- Offline end-to-end: server + dashboard screenshots in both themes and at phone width.
- **Live LLM check:** if API credentials are available in this session, run `llm.extract` on the
  six fixture texts from Task 2 and compare to hand-read numbers (≈ a few cents); otherwise say
  it was not run.
- **Not verifiable here:** live t.me / Wikipedia / RSS fetches (proxy blocks them) — the final
  report states this plainly and points to the README first-live-run checklist.
