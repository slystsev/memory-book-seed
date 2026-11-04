"""Public Telegram channel web preview (https://t.me/s/<channel>), paginated with ?before=<id>."""
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from powx.models import Item


def to_utc(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(timezone.utc).isoformat()


def parse_page(html: str) -> tuple[list[Item], str | None]:
    """Return (posts sorted by id, the page's 'older' cursor from <link rel=prev> or None)."""
    soup = BeautifulSoup(html, "lxml")
    out = []
    for div in soup.select("div.tgme_widget_message[data-post]"):
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
    prev = soup.select_one("link[rel=prev][href]")
    m = re.search(r"before=(\d+)", prev["href"]) if prev else None
    return sorted(out, key=lambda i: int(i.external_id)), (m[1] if m else None)


def page_url(channel, before=None):
    return f"https://t.me/s/{channel}" + (f"?before={before}" if before else "")


def iter_older(channel, before, http, stop_date):
    """Yield pages walking back in time until stop_date or the channel's first post."""
    while True:
        items, prev = parse_page(http(page_url(channel, before)))
        if not items:
            return
        yield items
        nxt = prev or items[0].external_id
        if items[0].published_at < stop_date or (before and int(nxt) >= int(before)):
            return
        before = nxt


def iter_newer(channel, after_id, http):
    """Yield pages of posts newer than after_id (None -> only the newest page)."""
    before = None
    while True:
        items, prev = parse_page(http(page_url(channel, before)))
        new = [i for i in items if after_id is None or int(i.external_id) > int(after_id)]
        if new:
            yield new
        if not items or after_id is None or len(new) < len(items):
            return
        before = prev or items[0].external_id
