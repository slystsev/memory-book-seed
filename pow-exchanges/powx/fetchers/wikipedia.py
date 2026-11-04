"""English Wikipedia seed (tier 3, reference only).

The article has no exchange table, so we take (a) prose paragraphs mentioning exchanges and
(b) the article's cited references whose headline mentions an exchange — those carry a
machine-readable date (COinS `rft.date`) and the original article URL. Both go through the
normal prefilter -> LLM path. Wikipedia-derived items are never chosen as primary source while
an official or media mention of the same exchange exists.
"""
import json
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote

from bs4 import BeautifulSoup

from powx.models import Item
from powx.prefilter import text_hash

API = "https://en.wikipedia.org/w/api.php"
RELEVANT = re.compile(r"exchang|swap|bring home|brought home|repatriat|returned|bodies", re.I)


def _clean(text):
    text = re.sub(r"\[\s*[\w\s]+\s*\]", "", text)          # [ 75 ], [note 3]
    return re.sub(r"\s+", " ", text).replace(" .", ".").replace(" ,", ",").strip(" ^")


def parse(raw_json, now):
    data = json.loads(raw_json)["parse"]
    page_url = "https://en.wikipedia.org/wiki/" + quote(data["title"].replace(" ", "_"))
    soup = BeautifulSoup(data["text"], "lxml")
    out = []
    for p in soup.select("p"):
        text = _clean(p.get_text(" ", strip=True))
        if re.search(r"exchang|swap", text, re.I):
            out.append(Item(f"wiki:p:{text_hash(text)[:16]}", page_url, now, text))
    for li in soup.select("ol.references > li"):
        ref = li.select_one(".reference-text")
        if ref is None:
            continue
        coins = ref.select_one("span.Z3988[title]")
        meta = parse_qs(coins["title"]) if coins else {}
        text = _clean(ref.get_text(" ", strip=True))
        if not RELEVANT.search(text):
            continue
        link = ref.select_one("a.external[href]")
        url = link["href"] if link else page_url
        date = (meta.get("rft.date") or [""])[0]
        published = f"{date}T12:00:00+00:00" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) else now
        out.append(Item(f"wiki:ref:{text_hash(url + text)[:16]}", url, published, text))
    return out


def fetch(title, http, now=None):
    now = now or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    t = quote(title.replace(" ", "_"))
    raw = http(f"{API}?action=parse&page={t}&prop=text&formatversion=2&format=json&redirects=1")
    return parse(raw, now)
