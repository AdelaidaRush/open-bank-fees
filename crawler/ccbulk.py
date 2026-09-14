"""Bulk lookup in a Common Crawl snapshot without touching index.commoncrawl.org.

The index server is meant for occasional queries: on 14.09 a probe with eight workers asking it about
thirty domains got our address refused. Common Crawl publishes the same index as files on
data.commoncrawl.org. `cluster.idx` (about 100 MB) says which compressed block of which `cdx-NNNNN.gz`
holds a given SURT key range. We download it once, binary-search every domain locally, and fetch only
the few hundred kilobytes each domain needs, in parallel, from the data host that is built for this.
"""
import bisect, gzip, io, json, os, re, threading, urllib.request
from concurrent.futures import ThreadPoolExecutor
from . import config
from .ccindex import WANT, SKIP, score

BASE = config.CC_DATA + "cc-index/collections/{crawl}/indexes/"


def surt_prefix(domain):
    """firsthorizon.com -> com,firsthorizon)/ ; bank.lendingclub.com -> com,lendingclub,bank)/"""
    parts = [p for p in domain.lower().split(".") if p and p != "www"]
    return ",".join(reversed(parts)) + ")/"


class Snapshot:
    def __init__(self, crawl):
        self.crawl = crawl
        self.dir = f"{config.HOME}/ccindex/{crawl}"
        os.makedirs(self.dir, exist_ok=True)
        self.keys, self.blocks = [], []
        self._load_cluster()

    def _load_cluster(self):
        path = f"{self.dir}/cluster.idx"
        if not os.path.exists(path):
            tmp = path + ".part"
            req = urllib.request.Request(BASE.format(crawl=self.crawl) + "cluster.idx", headers={"User-Agent": config.UA})
            with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "wb") as fh:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
            os.replace(tmp, path)
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                head, cdx, off, ln, _ = line.rstrip("\n").split("\t")
                self.keys.append(head.split(" ", 1)[0])
                self.blocks.append((cdx, int(off), int(ln)))

    def blocks_for(self, prefix):
        """Blocks whose key range can hold keys starting with prefix. Each cluster.idx line is the first key of
        a block, so we need the block that starts at or before the prefix and every block that starts inside
        the prefix range; the first block starting past that range cannot hold it."""
        hi = prefix[:-1] + chr(ord(prefix[-1]) + 1)
        i = max(bisect.bisect_right(self.keys, prefix) - 1, 0)
        j = bisect.bisect_left(self.keys, hi)
        return list(range(i, max(j, i + 1)))

    def read_block(self, i, cache, lock):
        with lock:
            if i in cache:
                return cache[i]
        cdx, off, ln = self.blocks[i]
        url = BASE.format(crawl=self.crawl) + cdx
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, headers={"Range": f"bytes={off}-{off + ln - 1}", "User-Agent": config.UA})
                data = gzip.decompress(urllib.request.urlopen(req, timeout=120).read()).decode("utf-8", "ignore")
                break
            except Exception:
                data = None
        with lock:
            cache[i] = data
        return data


def lookup(targets, crawls=None, workers=16, per_domain=None):
    """For every target domain, the best candidate pages across snapshots. Returns {domain: [records]}."""
    crawls = crawls or config.CC_CRAWLS
    per_domain = per_domain or config.MAX_PAGES_PER_DOMAIN
    found = {t["domain"]: {} for t in targets}
    for crawl in crawls:
        snap = Snapshot(crawl)
        need = {}
        for t in targets:
            p = surt_prefix(t["domain"])
            for b in snap.blocks_for(p):
                need.setdefault(b, []).append((t["domain"], p))
        cache, lock = {}, threading.Lock()
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(lambda b: snap.read_block(b, cache, lock), need))
        for b, doms in need.items():
            data = cache.get(b)
            if not data:
                continue
            for line in data.splitlines():
                key = line.split(" ", 1)[0]
                for dom, p in doms:
                    if not key.startswith(p):
                        continue
                    try:
                        rec = json.loads(line.split(" ", 2)[2])
                    except Exception:
                        continue
                    u, mime = rec.get("url", ""), rec.get("mime", "")
                    if rec.get("status") != "200" or SKIP.search(u) or not WANT.search(u):
                        continue
                    if not ("html" in mime or "pdf" in mime):
                        continue
                    rec["timestamp"] = line.split(" ", 2)[1]
                    rec["crawl"] = crawl
                    k = u.split("#")[0].split("?")[0].rstrip("/")
                    cur = found[dom].get(k)
                    if cur is None or rec["timestamp"] > cur["timestamp"]:
                        found[dom][k] = rec
        print(f"  {crawl}: {len(need)} index blocks read, "
              f"{sum(1 for d in found if found[d])} of {len(found)} domains have pages so far", flush=True)
    return {d: sorted(v.values(), key=lambda r: -score(r["url"], r.get("mime")))[:per_domain] for d, v in found.items()}
