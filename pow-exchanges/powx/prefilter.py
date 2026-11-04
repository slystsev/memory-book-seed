"""Cheap recall-oriented filter: decides only whether a text is worth an LLM call.

False positives cost one cheap LLM call; false negatives lose data. Never extracts numbers.
"""
import hashlib
import re

KEYWORDS = re.compile(
    r"обмін|обмен|exchang|swap|полон|плен|\bpows?\b|prisoner|captiv|"
    r"повернул|повертаються|вернул|возвращен|вдома|додому|returned home|brought home|"
    r"тіла|тела|bodies|репатріац|репатриац", re.I)


def is_candidate(text: str) -> bool:
    return bool(text and KEYWORDS.search(text))


def text_hash(text: str) -> str:
    t = re.sub(r"https?://\S+", " ", text.lower())
    t = re.sub(r"\W+", " ", t).strip()
    return hashlib.sha1(t.encode()).hexdigest()
