"""Second archive: the Internet Archive's Wayback Machine, for domains Common Crawl does not hold.

The Wayback CDX server sheds load with an HTML "Temporarily Offline" page, so every request here goes through
one shared throttle, retries with growing pauses, and gives up on a domain rather than hammering the service.
It is slow on purpose: a few seconds between requests, one domain at a time.
"""
import json, re, threading, time, urllib.parse, urllib.request
from . import config
from .ccindex import WANT, SKIP, score

CDX = "https://web.archive.org/cdx/search/cdx"
_lock = threading.Lock()
_last = [0.0]
GAP = 3.0          # seconds between any two requests to web.archive.org


def _polite():
    with _lock:
        wait = _last[0] + GAP - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()


def _get(url, timeout=90, tries=5, binary=False):
    for attempt in range(tries):
        _polite()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": config.UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read(config.MAX_BYTES)
                ctype = r.headers.get("Content-Type", "")
            if not binary and b"Temporarily Offline" in body[:600]:
                raise IOError("wayback offline")
            return body, ctype
        except urllib.error.HTTPError as e:
            if e.code in (404, 403):
                return None, None
            time.sleep(10 * (attempt + 1))
        except Exception:
            time.sleep(10 * (attempt + 1))
    return None, "gave up"


def find_pages(domain, limit=None):
    limit = limit or config.MAX_PAGES_PER_DOMAIN
    q = CDX + "?" + urllib.parse.urlencode({"url": f"{domain}/*", "output": "json", "filter": "statuscode:200",
                                            "collapse": "urlkey", "fl": "original,mimetype,timestamp,length",
                                            "limit": "5000"})
    body, st = _get(q)
    if body is None:
        return None if st == "gave up" else []
    try:
        rows = json.loads(body)[1:]
    except Exception:
        return None
    best = {}
    for url, mime, ts, ln in rows:
        if SKIP.search(url) or not WANT.search(url) or not ("html" in mime or "pdf" in mime):
            continue
        k = url.split("#")[0].split("?")[0].rstrip("/")
        if k not in best or ts > best[k]["timestamp"]:
            best[k] = {"url": url, "mime": mime, "timestamp": ts, "crawl": "wayback"}
    return sorted(best.values(), key=lambda r: -score(r["url"], r["mime"]))[:limit]


def fetch(rec):
    """The archived bytes exactly as captured: the id_ form serves them without the Wayback toolbar."""
    body, ctype = _get(f"https://web.archive.org/web/{rec['timestamp']}id_/{rec['url']}", binary=True)
    return body
