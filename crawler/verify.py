"""A fact stands only if its line can be found again, word for word, in the page text we stored."""
import re

_ws = re.compile(r"\s+")


def norm(s):
    return _ws.sub(" ", s or "").strip().lower()


def check(fact, text):
    if fact.get("quote") is None:
        # a rails list carries no single line; each rail name must appear in the text
        vals = fact.get("value") or []
        return all(v.lower() in text.lower() for v in vals)
    return norm(fact["quote"]) in norm(text)
