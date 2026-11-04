"""Group POW mentions into exchange events; pick consensus numbers and the primary source.

Rules
- A mention with numbers joins the closest event whose anchor is <= 36 h away and whose consensus
  numbers are within +-2 on every side both know; otherwise it founds a new event.
- Mentions without numbers only attach (never found an event).
- Consensus per side: mode of tier-1 sources of that side -> else tier <= 2 -> else all.
- Primary = earliest non-copy mention of the best tier (1 -> 2 -> 3). Copy = forwarded post or
  a text identical (normalised hash) to an earlier one.
- Effective time = the exchange date the LLM read from the text, else publication time.
- Tier-3 (reference) mentions take part only when the LLM found an exchange date.
"""
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

WINDOW = timedelta(hours=36)
TOL = 2
SIDES = (("n_to_ua", "ua"), ("n_to_ru", "ru"))


@dataclass
class M:
    id: int
    source_id: str
    tier: int
    side: str
    published_at: datetime
    n_to_ua: int | None
    n_to_ru: int | None
    is_copy: bool
    url: str


@dataclass
class Event:
    anchor: datetime
    mentions: list = field(default_factory=list)
    n_to_ua: int | None = None
    n_to_ru: int | None = None
    primary: M | None = None
    source_count: int = 0


def consensus(ms, attr, side):
    pools = ([x for x in ms if x.tier == 1 and x.side == side], [x for x in ms if x.tier <= 2], ms)
    for pool in pools:
        vals = [getattr(x, attr) for x in pool if getattr(x, attr) is not None]
        if vals:
            top = Counter(vals).most_common()
            best = top[0][1]
            return max(v for v, c in top if c == best)   # tie -> larger (corrections add people)
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


def recluster(con):
    """Recompute all non-overridden events from mentions. Idempotent."""
    with con:
        con.execute("""UPDATE mentions SET event_id=NULL WHERE event_id IN
                       (SELECT id FROM events WHERE manual_override=0)""")
        con.execute("DELETE FROM events WHERE manual_override=0")
        rows = con.execute("""SELECT m.*, s.tier, s.side,
                                coalesce(m.exchange_date || 'T12:00:00+00:00', m.published_at) AS t
                              FROM mentions m JOIN sources s ON s.id=m.source_id
                              WHERE m.kind='pow' AND m.event_id IS NULL
                                AND NOT (s.tier=3 AND m.exchange_date IS NULL)
                              ORDER BY t, m.id""").fetchall()
        seen, ms = set(), []
        for r in rows:
            ms.append(M(r["id"], r["source_id"], r["tier"], r["side"], datetime.fromisoformat(r["t"]),
                        r["n_to_ua"], r["n_to_ru"],
                        r["forwarded_from"] is not None or r["text_hash"] in seen, r["url"]))
            seen.add(r["text_hash"])
        for e in cluster(ms):
            p = e.primary
            url = p.url
            if p.is_copy:   # only copies exist -> point at the original post if known
                url = con.execute("SELECT forwarded_from FROM mentions WHERE id=?", (p.id,)).fetchone()[0] or p.url
            cur = con.execute("""INSERT INTO events(date, n_to_ua, n_to_ru, primary_mention_id, primary_url,
                                 mention_count, source_count) VALUES(?,?,?,?,?,?,?)""",
                              (min(x.published_at for x in e.mentions).date().isoformat(),
                               e.n_to_ua, e.n_to_ru, p.id, url, len(e.mentions), e.source_count))
            con.executemany("UPDATE mentions SET event_id=? WHERE id=?",
                            [(cur.lastrowid, x.id) for x in e.mentions])
