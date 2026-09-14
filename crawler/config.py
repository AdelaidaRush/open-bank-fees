import os

# where the page text and results live; never inside the repository, the collected data is not public
HOME = os.environ.get("CRAWLER_HOME", os.path.expanduser("~/open-bank-fees-data"))
UA = os.environ.get("CRAWLER_UA", "open-bank-fees/0.1 (+https://github.com/AdelaidaRush/open-bank-fees)")
# the three most recent Common Crawl snapshots are asked in turn; a page missing from one is often in another
CC_CRAWLS = os.environ.get("CC_CRAWLS", "CC-MAIN-2026-34,CC-MAIN-2026-30,CC-MAIN-2026-25").split(",")
CC_INDEX = "https://index.commoncrawl.org/{crawl}-index"
CC_DATA = "https://data.commoncrawl.org/"
MAX_PAGES_PER_DOMAIN = int(os.environ.get("MAX_PAGES", "25"))
MAX_BYTES = 12_000_000
os.makedirs(HOME, exist_ok=True)
