import time
import urllib.error
import urllib.request

UA = "powx/0.1 (POW exchange tracker; +https://github.com/slystsev/memory-book-seed)"
RETRYABLE = (429, 500, 502, 503, 504)
MAX_WAIT = 120


def _wait_for(err, default):
    try:
        return min(MAX_WAIT, max(default, int(err.headers.get("Retry-After", ""))))
    except (TypeError, ValueError, AttributeError):
        return default


def get(url, *, retries=4, throttle=1.5, timeout=30, sleep=time.sleep) -> str:
    """GET with a polite throttle; retries 429/5xx/network errors, honouring Retry-After."""
    delay = 2
    for attempt in range(retries + 1):
        sleep(throttle)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode(r.headers.get_content_charset() or "utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code not in RETRYABLE or attempt == retries:
                raise
            sleep(_wait_for(e, delay))
        except urllib.error.URLError:
            if attempt == retries:
                raise
            sleep(delay)
        delay *= 2
