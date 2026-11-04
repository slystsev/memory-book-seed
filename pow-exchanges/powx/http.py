import time
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (compatible; powx/0.1; POW exchange tracker; +https://github.com/slystsev/memory-book-seed)"


def get(url, *, retries=4, throttle=1.5, timeout=30) -> str:
    """GET with a polite throttle and exponential backoff on 429/5xx/network errors."""
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
        time.sleep(delay)
        delay *= 2
