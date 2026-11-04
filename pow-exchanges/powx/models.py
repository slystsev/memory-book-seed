from dataclasses import dataclass


@dataclass
class Item:
    """One raw post/article/paragraph produced by a fetcher (before LLM extraction)."""
    external_id: str
    url: str
    published_at: str            # UTC ISO-8601
    text: str
    forwarded_from: str | None = None
