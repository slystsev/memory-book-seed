# powx: Russia–Ukraine POW exchange tracker

Collects every public mention of prisoner-of-war exchanges between Russia and Ukraine, uses Claude
to extract the numbers, merges duplicate mentions into a single **exchange event**, picks each
event's **primary source**, and serves a dashboard with the totals.

It is independent of the memory-book project in the rest of this repository.

```
sources ──► fetchers ──► keyword prefilter ──► SQLite (mentions) ──► Claude extraction ──► clustering ──► events ──► API + dashboard
            telegram     (send to LLM or not)                          (sync or Batches)    (dedup, primary)
            rss
            wikipedia
```

## Quick start

```bash
cd pow-exchanges
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...            # or: ant auth login
export POWX_MODEL=claude-haiku-5-5      # default; e.g. claude-opus-5-5 for higher accuracy

# 1. Pull history back to 24.02.2022 (resumable — rerun after any interruption)
python -m powx.crawl backfill

# 2. Cost gate: extract 200 posts synchronously, look at results + token usage before the big batch
python -c "from powx import db, llm; print(llm.process_pending(db.connect('powx.db'), llm.make_client(), limit=200))"
python -m powx.llm_batch status

# 3. Extract the rest through the Message Batches API (50 % cheaper, finishes within 24 h)
python -m powx.llm_batch submit         # repeat until it prints None (10 000 posts per batch)
python -m powx.llm_batch collect        # repeat every ~10 min until no batch is 'submitted'

# 4. Serve the dashboard; it re-crawls and extracts new posts every 30 min
python -m powx.crawl update             # once, to cluster everything collected so far
python -m powx.server --host 0.0.0.0 --port 8000 --interval 1800
```

Docker: `docker build -t powx . && docker run -d -p 8000:8000 -v powx-data:/data -e ANTHROPIC_API_KEY=... powx`
(run the backfill steps once inside the container with `docker exec`, pointing `--db /data/powx.db`).

Useful flags: `crawl --only koord_shtab,mod_russia`, `crawl update --no-llm`, `server --no-llm`,
`server --interval 0` (no background updates).

## Sources (`sources.json`)

| id | kind | side | tier |
|---|---|---|---|
| `koord_shtab` — Coordination HQ for the Treatment of POWs (t.me/Koord_Shtab) | telegram | ua | 1 |
| `zelenskiy` — t.me/V_Zelenskiy_official | telegram | ua | 1 |
| `gur` — Defence Intelligence of Ukraine, t.me/DIUkraine | telegram | ua | 1 |
| `mod_russia` — Russian Ministry of Defence, t.me/mod_russia | telegram | ru | 1 |
| `pravda_ua` — Ukrainska Pravda RSS | rss | ua | 2 |
| `tass` — TASS RSS | rss | ru | 2 |
| `wikipedia` — en article on POWs in the war: prose + cited news references | wikipedia | neutral | 3 |

Tier 1 = official, 2 = media, 3 = reference only (never chosen as primary while a tier 1/2 mention
of the same exchange exists; such events show "no primary source found").

**Not included — handle needed:** the Ukrainian ombudsman (Lubinets) and the Russian ombudsman
(Moskalkova). The handles tried (`dmytro_lubinets`, `moskalkova_tatiana`, …) have no public web
preview. Add the right handle to `sources.json` if you know it; check `/api/sources` for
`last_error` after the next run.

Telegram is read from the public preview `https://t.me/s/<channel>` (no account, no API key).
RSS feeds only expose recent items, so they contribute to incremental updates, not history.

## How a post becomes an exchange

1. **Prefilter** (`powx/prefilter.py`): a broad keyword regex (обмін/обмен/exchange/полон/плен/POW/
   повернул…/тіла…). It only decides whether the LLM sees the post; it is tuned to let too much
   through rather than miss anything.
2. **Claude extraction** (`powx/llm.py`): structured JSON with
   `report_type` (`exchange_event` · `cumulative_total` · `negotiation_or_plan` ·
   `bodies_repatriation` · `other`), people returned to each side, civilians, the exchange date,
   and a **verbatim quote** the numbers come from (shown on the dashboard for checking).
   Only `exchange_event` is counted — running totals ("4,000 returned since 2022"), plans and
   bodies are stored but not counted. Refused/truncated answers are retried (max 3 attempts).
3. **Dedup and clustering** (`powx/cluster.py`):
   - the same post is stored once per source (`UNIQUE(source, external_id)`);
   - forwards and identical texts (normalised hash) are marked as copies;
   - mentions within **36 h** whose numbers agree within **±2** form one event; different numbers
     on the same day are separate exchanges; mentions without numbers only attach;
   - a post that names an earlier exchange date is placed on that date.
4. **Numbers per event:** for "returned to Ukraine", the most common value among Ukrainian
   official sources (then all tier 1–2, then all); the same for Russia with Russian sources.
5. **Primary source:** the earliest original (non-copy) mention from the best tier.

### Manual corrections

```sql
-- fix an event; it will not be recomputed again
UPDATE events SET n_to_ua = 103, n_to_ru = 103, manual_override = 1 WHERE id = 42;
```

## API

`/api/stats` · `/api/monthly` · `/api/events` · `/api/events/<id>/mentions` · `/api/sources` · `/healthz`

## Tests

```bash
python -m unittest -v
```

All tests are offline. Fetcher tests include fixtures saved from the live sources (Telegram,
both RSS feeds, Wikipedia), and LLM tests use a fake client. Dashboard screenshots can be made
from a DEMO database: `python -m tests.fixtures.demo_seed /tmp/demo.db` then
`python -m powx.server --db /tmp/demo.db --interval 0`.

## Known limits

- Numbers come from an LLM reading text. Check outliers using the quote on each mention, and use
  `manual_override` to fix them.
- Wikipedia rate-limits shared IPs (HTTP 429); the client honours `Retry-After`.
- A Telegram preview page holds only 5–20 posts, so a full backfill of a large channel takes
  thousands of requests (1.5 s apart). Expect about an hour per channel.
- Event ids change when events are recomputed; link to events by date.
