"""Find a domain's fee, pricing and terms pages inside Common Crawl snapshots."""
import json, re, time, urllib.parse, urllib.request
from . import config

WANT = re.compile(
    r"(fee|fees|pricing|price|tariff|charges|schedule|rates|business|commercial|corporate|treasury|"
    r"checking|account|wire|transfer|international|foreign|currenc|terms|conditions|agreement|"
    r"disclosure|eligib|requirement|open|small-?business|merchant|payments?)", re.I)
SKIP = re.compile(r"(\.(jpe?g|png|gif|svg|webp|css|js|ico|woff2?|mp4|zip)(\?|$)|/(careers|jobs|news|press|blog|"
                  r"events|investor|ir/|media-?room|locations?|branch|atm)(/|$)|login|signin|cookie|privacy)", re.I)
STRONG = re.compile(r"(fee[-_ ]?schedule|schedule[-_ ]?of[-_ ]?(fees|charges)|business[-_ ]?(checking|account|banking)|"
                    r"pricing|tariff|commercial[-_ ]?(checking|account)|account[-_ ]?agreement|fees?)", re.I)


def _get_json_lines(url, timeout=90, tries=4):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": config.UA})
            body = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
            return [json.loads(l) for l in body.splitlines() if l.startswith("{")]
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []          # the snapshot holds nothing for this domain
            time.sleep(3 * (attempt + 1))
        except Exception:
            time.sleep(3 * (attempt + 1))
    return None                    # the index did not answer; the caller records it, it is not "no pages"


def score(url, mime):
    """Order candidates: a business fee schedule PDF first, generic pages last."""
    s = 0
    if STRONG.search(url):
        s += 5
    if "pdf" in (mime or ""):
        s += 3
    s += len(WANT.findall(url))
    return s


def find_pages(domain, crawls=None, limit=None):
    """Best candidate records for a domain across snapshots, newest capture of each URL wins."""
    crawls = crawls or config.CC_CRAWLS
    limit = limit or config.MAX_PAGES_PER_DOMAIN
    best, asked, failed = {}, 0, 0
    for crawl in crawls:
        q = (config.CC_INDEX.format(crawl=crawl) + "?" + urllib.parse.urlencode({
            "url": f"{domain}/*", "output": "json", "filter": "status:200",
            "fl": "url,mime,status,length,filename,offset,digest,timestamp"}))
        rows = _get_json_lines(q)
        asked += 1
        if rows is None:
            failed += 1
            continue
        for r in rows:
            u = r.get("url", "")
            if SKIP.search(u) or not WANT.search(u):
                continue
            mime = r.get("mime", "")
            if not ("html" in mime or "pdf" in mime):
                continue
            key = u.split("#")[0].split("?")[0].rstrip("/")
            if key not in best or r.get("timestamp", "") > best[key].get("timestamp", ""):
                r["crawl"] = crawl
                best[key] = r
        if len(best) >= limit * 2:
            break
    ranked = sorted(best.values(), key=lambda r: -score(r["url"], r.get("mime")))
    return ranked[:limit], {"asked": asked, "failed": failed, "candidates": len(best)}
