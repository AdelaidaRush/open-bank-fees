"""Which domains to read, taken from the index's own base and cut into shards."""
import os, sqlite3, zlib

# the list of institutions comes from the operator's own base; there is no default path in public code
DEFAULT_DB = os.environ.get("REGISTRY_DB", "registry.db")

BANK_KINDS = ("bank", "credit_union", "building_society", "emi_payments", "card_processor", "remittance", "vasp")


def domain_of(url):
    if not url:
        return None
    d = url.strip().lower().replace("https://", "").replace("http://", "").split("/")[0].split("?")[0]
    d = d[4:] if d.startswith("www.") else d
    return d if "." in d and " " not in d else None


def load(db=DEFAULT_DB, kinds=BANK_KINDS, limit=None):
    """Distinct domains of live institutions of the given kinds, heaviest first. One domain can belong to
    several register rows; it is read once and the result is attached to every slug that shares it."""
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    q = ("SELECT e.slug, e.name, e.country, COALESCE(f.website, e.domain) AS site, e.priority "
         "FROM entity e LEFT JOIN facts f ON f.slug = e.slug "
         f"WHERE e.stage IN ('queued','researched') AND e.entity_type IN ({','.join('?'*len(kinds))}) "
         "AND COALESCE(f.website, e.domain) IS NOT NULL ORDER BY e.priority DESC, e.slug")
    by_domain = {}
    for slug, name, country, site, pri in c.execute(q, kinds):
        d = domain_of(site)
        if not d:
            continue
        t = by_domain.setdefault(d, {"domain": d, "slugs": [], "name": name, "country": country, "priority": pri})
        t["slugs"].append(slug)
    out = list(by_domain.values())
    return out[:limit] if limit else out


def shard(targets, i, n):
    """Stable shard by domain: the same domain always lands on the same worker, whatever the order."""
    return [t for t in targets if zlib.crc32(t["domain"].encode()) % n == i]
