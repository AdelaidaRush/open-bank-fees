"""open-bank-fees command line.

  python -m crawler.cli run --shard 0 --of 1 --limit 100 --workers 8
  python -m crawler.cli status
  python -m crawler.cli export --out results.jsonl
"""
import argparse, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from . import config, targets as T, ccindex, ccbulk, wayback, fetch, extract, verify
from .warehouse import Warehouse


def dedupe(facts):
    """One line repeated across a site's pages (tabs, mobile copies, footers) is one fact."""
    import re as _re
    seen, out = set(), []
    for f in facts:
        k = (f["field"], _re.sub(r"\W+", " ", (f.get("quote") or "")).strip().lower(), str(f.get("value")))
        if k not in seen:
            seen.add(k); out.append(f)
    return out


def one_domain(wh, t, recs=None):
    meta = {"failed": 0}
    if recs is None:                      # the slow per-domain path, kept for a single domain check
        recs, meta = ccindex.find_pages(t["domain"])
        if meta["failed"] and meta["failed"] == meta["asked"]:
            wh.done(t["domain"], t["slugs"], "index_unreachable", 0, 0, meta["failed"])
            return {"domain": t["domain"], "status": "index_unreachable"}
    kept, facts, rejected = 0, [], 0
    for rec in recs:
        page = fetch.to_text(rec)
        if not page or not (page["text"] or "").strip():
            continue
        sha = wh.put(t["domain"], rec, page)
        kept += 1
        pm = {"url": rec["url"], "title": page["title"], "crawl": rec.get("crawl"),
              "captured": rec.get("timestamp"), "sha1": sha}
        for f in extract.facts(page["text"], pm):
            if verify.check(f, page["text"]):
                facts.append(f)
            else:
                rejected += 1
    facts = dedupe(facts)
    if facts:
        os.makedirs(f"{config.HOME}/facts", exist_ok=True)
        with open(f"{config.HOME}/facts/{t['domain']}.jsonl", "w") as fh:
            for f in facts:
                fh.write(json.dumps({"domain": t["domain"], "slugs": t["slugs"], **f}, ensure_ascii=False) + "\n")
    status = "facts" if facts else ("pages" if kept else ("no_pages" if not recs else "unreadable"))
    wh.done(t["domain"], t["slugs"], status, kept, len(facts), meta["failed"])
    return {"domain": t["domain"], "status": status, "pages": kept, "facts": len(facts), "rejected": rejected}


def cmd_run(a):
    wh = Warehouse()
    ts = T.shard(T.load(limit=a.limit), a.shard, a.of)
    todo = [t for t in ts if a.again or not wh.seen(t["domain"])]
    print(f"shard {a.shard}/{a.of}: {len(ts)} domains, {len(todo)} to read, {a.workers} workers", flush=True)
    t0, n, agg = time.time(), 0, {}
    # find pages for the whole shard at once from the published index files, never the index server
    print("looking up pages in Common Crawl index files", flush=True)
    pages = ccbulk.lookup(todo, workers=a.workers * 2)
    print(f"lookup done in {time.time()-t0:.0f}s, reading pages", flush=True)
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(one_domain, wh, t, pages.get(t["domain"], [])) for t in todo]
        for fu in as_completed(futs):
            try:
                r = fu.result()
            except Exception as e:
                r = {"status": "error", "error": str(e)[:120]}
            n += 1
            agg[r["status"]] = agg.get(r["status"], 0) + 1
            if n % 10 == 0 or n == len(todo):
                rate = n / max(time.time() - t0, 1) * 3600
                print(f"  {n}/{len(todo)}  {agg}  ~{rate:.0f} domains/hour", flush=True)
    print(json.dumps({"shard": a.shard, "of": a.of, "done": n, "by_status": agg,
                      "seconds": round(time.time() - t0)}, ensure_ascii=False))


def cmd_reextract(a):
    """Run the extraction rules again over every stored page. No page is downloaded: this is what the
    warehouse is for, and why a better rule costs nothing to apply to everything read so far."""
    wh = Warehouse()
    os.makedirs(f"{config.HOME}/facts", exist_ok=True)
    domains = [r[0] for r in wh.db.execute("SELECT DISTINCT domain FROM page")]
    total, rej, with_facts = 0, 0, 0
    for d in domains:
        slugs = json.loads((wh.db.execute("SELECT slugs FROM domain_run WHERE domain=?", (d,)).fetchone() or ["[]"])[0])
        facts = []
        for sha, url, kind, title, crawl, captured in wh.pages(d):
            text = wh.text(sha)
            for f in extract.facts(text, {"url": url, "title": title, "crawl": crawl, "captured": captured, "sha1": sha}):
                if verify.check(f, text):
                    facts.append(f)
                else:
                    rej += 1
        facts = dedupe(facts)
        path = f"{config.HOME}/facts/{d}.jsonl"
        if facts:
            with open(path, "w") as fh:
                for f in facts:
                    fh.write(json.dumps({"domain": d, "slugs": slugs, **f}, ensure_ascii=False) + "\n")
            with_facts += 1
        elif os.path.exists(path):
            os.remove(path)
        total += len(facts)
    print(f"re-extracted {len(domains)} domains from the warehouse: {with_facts} with facts, {total} facts, {rej} rejected by verify")


def cmd_wayback(a):
    """Domains Common Crawl had nothing for, read from the Wayback Machine, slowly and one at a time."""
    wh = Warehouse()
    ts = {t["domain"]: t for t in T.load()}
    todo = [d for (d,) in wh.db.execute("SELECT domain FROM domain_run WHERE status='no_pages' ORDER BY domain")]
    done = {d for (d,) in wh.db.execute("SELECT domain FROM domain_run WHERE status LIKE 'wb_%'")}
    todo = [d for d in todo if d in ts and d not in done][: a.limit or None]
    print(f"wayback: {len(todo)} domains without Common Crawl pages", flush=True)
    t0, agg = time.time(), {}
    for i, d in enumerate(todo, 1):
        recs = wayback.find_pages(d)
        if recs is None:
            status = "wb_unreachable"; r = {"status": status}
            wh.done(d, ts[d]["slugs"], status, 0, 0, 1)
        else:
            r = one_domain(wh, ts[d], recs)
            status = "wb_" + r["status"]
            wh.db.execute("UPDATE domain_run SET status=? WHERE domain=?", (status, d)); wh.db.commit()
        agg[status] = agg.get(status, 0) + 1
        if i % 10 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)} {agg} ~{i/max(time.time()-t0,1)*3600:.0f} domains/hour", flush=True)
    print(json.dumps({"wayback_done": len(todo), "by_status": agg}))


def cmd_status(a):
    wh = Warehouse()
    q = lambda s: wh.db.execute(s).fetchall()
    print("domains by status:", dict(q("SELECT status, COUNT(*) FROM domain_run GROUP BY 1")))
    print("pages stored:", q("SELECT COUNT(*), COALESCE(SUM(chars),0) FROM page")[0])
    print("facts by field:")
    counts = {}
    for fn in os.listdir(f"{config.HOME}/facts") if os.path.isdir(f"{config.HOME}/facts") else []:
        for line in open(f"{config.HOME}/facts/{fn}"):
            f = json.loads(line)["field"]
            counts[f] = counts.get(f, 0) + 1
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {k:<22}{v}")


def cmd_export(a):
    n = 0
    with open(a.out, "w") as out:
        for fn in sorted(os.listdir(f"{config.HOME}/facts")):
            for line in open(f"{config.HOME}/facts/{fn}"):
                out.write(line); n += 1
    print(f"exported {n} facts to {a.out}")


def main():
    p = argparse.ArgumentParser(prog="crawler")
    s = p.add_subparsers(dest="cmd", required=True)
    r = s.add_parser("run")
    r.add_argument("--shard", type=int, default=0); r.add_argument("--of", type=int, default=1)
    r.add_argument("--limit", type=int, default=None); r.add_argument("--workers", type=int, default=8)
    r.add_argument("--again", action="store_true")
    r.set_defaults(f=cmd_run)
    s.add_parser("status").set_defaults(f=cmd_status)
    s.add_parser("reextract").set_defaults(f=cmd_reextract)
    w = s.add_parser("wayback"); w.add_argument("--limit", type=int, default=None); w.set_defaults(f=cmd_wayback)
    e = s.add_parser("export"); e.add_argument("--out", default="results.jsonl"); e.set_defaults(f=cmd_export)
    a = p.parse_args(); a.f(a)


if __name__ == "__main__":
    main()
