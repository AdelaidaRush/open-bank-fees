"""The page store. Every page text we used is kept once, compressed, keyed by the hash of its text, so the
extraction rules can be improved and re-run over everything without downloading a single page again."""
import gzip, hashlib, json, os, sqlite3, threading
from . import config

_lock = threading.Lock()


class Warehouse:
    def __init__(self, home=None):
        self.home = home or config.HOME
        os.makedirs(f"{self.home}/text", exist_ok=True)
        self.db = sqlite3.connect(f"{self.home}/warehouse.db", check_same_thread=False, timeout=60)
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS page (
              sha1 TEXT, domain TEXT, url TEXT, kind TEXT, title TEXT, crawl TEXT, captured TEXT,
              bytes INTEGER, chars INTEGER, PRIMARY KEY (domain, url));
            CREATE INDEX IF NOT EXISTS ix_page_domain ON page(domain);
            CREATE TABLE IF NOT EXISTS domain_run (
              domain TEXT PRIMARY KEY, slugs TEXT, status TEXT, pages INTEGER, facts INTEGER,
              index_failed INTEGER, updated TEXT);
        """)

    def put(self, domain, rec, page):
        text = page["text"] or ""
        sha = hashlib.sha1(text.encode()).hexdigest()
        path = f"{self.home}/text/{sha[:2]}/{sha}.txt.gz"
        with _lock:
            if not os.path.exists(path):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with gzip.open(path, "wt", encoding="utf-8") as fh:
                    fh.write(text)
            self.db.execute("INSERT OR REPLACE INTO page VALUES (?,?,?,?,?,?,?,?,?)",
                            (sha, domain, rec["url"], page["kind"], page.get("title"), rec.get("crawl"),
                             rec.get("timestamp"), page.get("bytes"), len(text)))
            self.db.commit()
        return sha

    def text(self, sha):
        with gzip.open(f"{self.home}/text/{sha[:2]}/{sha}.txt.gz", "rt", encoding="utf-8") as fh:
            return fh.read()

    def pages(self, domain):
        return self.db.execute("SELECT sha1, url, kind, title, crawl, captured FROM page WHERE domain=?",
                               (domain,)).fetchall()

    def done(self, domain, slugs, status, pages, facts, index_failed):
        with _lock:
            self.db.execute("INSERT OR REPLACE INTO domain_run VALUES (?,?,?,?,?,?,datetime('now'))",
                            (domain, json.dumps(slugs), status, pages, facts, index_failed))
            self.db.commit()

    def seen(self, domain):
        r = self.db.execute("SELECT status FROM domain_run WHERE domain=?", (domain,)).fetchone()
        return r[0] if r else None
