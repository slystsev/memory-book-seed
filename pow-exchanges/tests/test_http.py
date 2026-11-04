import io
import unittest
import urllib.error
from email.message import Message
from unittest import mock

from powx import http


def err(code, retry_after=None):
    h = Message()
    if retry_after is not None:
        h["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("u", code, "x", h, io.BytesIO(b""))


class Resp(io.BytesIO):
    headers = Message()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class HttpTest(unittest.TestCase):
    def test_honours_retry_after_then_succeeds(self):
        sleeps = []
        with mock.patch("urllib.request.urlopen", side_effect=[err(429, 29), Resp(b"ok")]):
            self.assertEqual(http.get("https://example.org/", sleep=sleeps.append), "ok")
        self.assertIn(29, sleeps)

    def test_retry_after_capped(self):
        sleeps = []
        with mock.patch("urllib.request.urlopen", side_effect=[err(503, 99999), Resp(b"ok")]):
            http.get("https://example.org/", sleep=sleeps.append)
        self.assertIn(http.MAX_WAIT, sleeps)

    def test_non_retryable_raises(self):
        with mock.patch("urllib.request.urlopen", side_effect=[err(404)]):
            with self.assertRaises(urllib.error.HTTPError):
                http.get("https://example.org/", sleep=lambda s: None)
