"""RSS 2.0 / Atom feeds. Feeds expose only recent items, so this source is incremental-only."""
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup

from powx.fetchers.telegram import to_utc
from powx.models import Item

A = "{http://www.w3.org/2005/Atom}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"


def _plain(html):
    return BeautifulSoup(html or "", "lxml").get_text(" ", strip=True) if html else ""


def _join(*parts):
    return "\n".join(p for p in parts if p)


def parse_feed(xml: str) -> list[Item]:
    root = ET.fromstring(xml)
    out = []
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        date = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc).isoformat()
        body = _plain(it.findtext(CONTENT)) or _plain(it.findtext("description"))
        out.append(Item((it.findtext("guid") or link).strip(), link, date,
                        _join(_plain(it.findtext("title")), body)))
    for e in root.iter(A + "entry"):
        link_el = e.find(A + "link")
        date = (e.findtext(A + "published") or e.findtext(A + "updated")).replace("Z", "+00:00")
        text = _join(_plain(e.findtext(A + "title")),
                     _plain(e.findtext(A + "content")) or _plain(e.findtext(A + "summary")))
        out.append(Item(e.findtext(A + "id"), link_el.get("href") if link_el is not None else "",
                        to_utc(date), text))
    return out


def fetch(url, http):
    return parse_feed(http(url))
