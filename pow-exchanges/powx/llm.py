"""Structured extraction of POW-exchange facts with Claude.

Every prefiltered candidate goes through `build_params` → Messages API (sync) or the
Message Batches API (backfill, see llm_batch.py) → `parse_message` → `apply`.
"""
import json
import logging
import os
import re

log = logging.getLogger("powx.llm")

DEFAULT_MODEL = "claude-haiku-5-5"
# Models with server-side refusal fallback (not Haiku).
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"

NULLABLE_INT = {"anyOf": [{"type": "integer"}, {"type": "null"}]}
SCHEMA = {
    "type": "object",
    "properties": {
        "report_type": {"type": "string", "enum": [
            "exchange_event", "cumulative_total", "negotiation_or_plan", "bodies_repatriation", "other"]},
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

SYSTEM = """You extract facts about prisoner exchanges between Russia and Ukraine from one \
Telegram post, news item or encyclopedia paragraph (Ukrainian, Russian or English).

report_type:
- exchange_event: the text reports a specific exchange or return of living prisoners \
(military or civilian) that has happened.
- cumulative_total: running totals ("since 2022, 4,000 returned"), statistics, anniversaries.
- negotiation_or_plan: talks, agreements, preparations, lists submitted, exchanges that have \
not happened yet.
- bodies_repatriation: return of bodies of the dead only.
- other: anything else (support for families, trials, captivity conditions, appeals).

returned_to_ukraine / returned_to_russia: the number of living people returned to that side in \
the exchange this text reports. Use null when the text does not state it. Do not infer one side \
from the other unless the text says the exchange was "N for N" or "N each". "Ours", "our \
defenders", "наших" mean the publisher's side, given below.
civilians_to_ukraine: civilians among those returned to Ukraine, only if stated.
exchange_date: YYYY-MM-DD only if the text states or clearly implies when the exchange happened \
("today" means the publication date); otherwise null.
quote: copy verbatim the sentence(s) the numbers come from; empty string if there are none."""

KIND = {"exchange_event": "pow", "bodies_repatriation": "bodies"}
COLS = ("llm_status", "llm_model", "kind", "report_type", "n_to_ua", "n_to_ru",
        "n_civilians_to_ua", "exchange_date", "quote")


def model_name():
    return os.environ.get("POWX_MODEL", DEFAULT_MODEL)


def build_params(text, side, published_at, model=None):
    return {
        "model": model or model_name(),
        "max_tokens": 4096,
        "system": SYSTEM,
        "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        "messages": [{"role": "user", "content":
                      f"Publisher side: {side}\nPublished at: {published_at}\n\n<post>\n{text}\n</post>"}],
    }


def parse_message(msg):
    """Map an API message to mention columns. Never raises on bad model output."""
    failed = {"llm_status": "failed", "llm_model": getattr(msg, "model", None)}
    if msg.stop_reason in ("refusal", "max_tokens"):
        return failed
    try:
        data = json.loads(next(b.text for b in msg.content if b.type == "text"))
        rtype = data["report_type"]
    except (StopIteration, json.JSONDecodeError, KeyError, TypeError):
        return failed
    date = data.get("exchange_date")
    if not (isinstance(date, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date)):
        date = None

    def num(k):
        v = data.get(k)
        return v if isinstance(v, int) and v >= 0 else None

    return {"llm_status": "done", "llm_model": msg.model, "kind": KIND.get(rtype, "other"),
            "report_type": rtype, "n_to_ua": num("returned_to_ukraine"),
            "n_to_ru": num("returned_to_russia"), "n_civilians_to_ua": num("civilians_to_ukraine"),
            "exchange_date": date, "quote": data.get("quote") or ""}


def extract(client, text, side, published_at, model=None):
    params = build_params(text, side, published_at, model)
    if params["model"] in FALLBACK_MODELS:
        msg = client.beta.messages.create(**params, betas=[FALLBACK_BETA], fallbacks="default")
    else:
        msg = client.messages.create(**params)
    return parse_message(msg)


def make_client():
    import anthropic
    return anthropic.Anthropic()   # default credential chain: ANTHROPIC_API_KEY or `ant auth login`


def apply(con, mention_id, result):
    cols = [c for c in COLS if c in result]
    with con:
        con.execute(f"UPDATE mentions SET {', '.join(c + '=?' for c in cols)} WHERE id=?",
                    [result[c] for c in cols] + [mention_id])


def process_pending(con, client, limit=500):
    """Synchronous extraction for incremental updates. API errors leave the row for retry."""
    import anthropic
    rows = con.execute("""SELECT m.id, m.text, m.published_at, s.side FROM mentions m
                          JOIN sources s ON s.id=m.source_id
                          WHERE m.llm_status IN ('pending','failed') AND m.llm_attempts < 3
                          ORDER BY m.published_at LIMIT ?""", (limit,)).fetchall()
    done = 0
    for r in rows:
        with con:
            con.execute("UPDATE mentions SET llm_attempts=llm_attempts+1 WHERE id=?", (r["id"],))
        try:
            apply(con, r["id"], extract(client, r["text"], r["side"], r["published_at"]))
            done += 1
        except anthropic.RateLimitError:
            log.warning("rate limited; stopping this round")
            break
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            log.warning("mention %s: %s", r["id"], e)
    return done
