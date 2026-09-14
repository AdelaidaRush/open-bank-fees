# open-bank-fees

Finds what banks publish about their business accounts: monthly fees and when they are waived, opening
deposits, wires, overdraft charges, FX mark-ups, currencies, payment rails. It reads **open web archives**,
not the banks' own servers, and keeps every fact together with the exact line it came from.

Released as open source so anyone can check how each number was found and reuse the method.

## How it works

```
domains ─► Common Crawl index files ─► archived page or PDF ─► text ─► rules ─► fact + its line ─► verify
```

1. **Find pages without asking anyone's server.** Common Crawl publishes its URL index as files. We download
   `cluster.idx` for a snapshot once, look up every domain locally, and fetch only the index blocks we need
   from `data.commoncrawl.org`. The index server `index.commoncrawl.org` is for occasional queries and is not
   used in bulk.
2. **Read the archived copy.** A range request pulls one record out of a WARC file. HTML becomes text with table
   cells kept apart; PDFs go through `pdftotext -layout`.
3. **Store the text.** Every page used is kept compressed and keyed by hash, so improved rules can be re-run over
   everything already read with `reextract`, without downloading again.
4. **Write only what a rule can prove.** A fact needs the thing and its value in one line. When a line mixes a fee
   with a balance or a threshold, the line is kept and no amount is written. Editorial pages, other banks'
   examples and promotions are skipped.
5. **Verify.** A fact whose line cannot be found again, word for word, in the stored text is rejected.

## Use

```bash
pip install -r requirements.txt           # plus poppler for pdftotext
python -m crawler.cli run --shard 0 --of 4 --workers 12
python -m crawler.cli reextract            # re-run the rules over stored pages
python -m crawler.cli status
python -m crawler.cli export --out facts.jsonl
```

Environment: `CRAWLER_HOME` (where text and facts are stored, never inside the repository),
`REGISTRY_DB` (list of institutions), `CC_CRAWLS` (snapshots to read).

## Running it on more machines

Collection runs on **self-hosted GitHub Actions runners**: machines the maintainers operate. GitHub's terms do not
allow GitHub-hosted runners to be used for work unrelated to building and testing the project, so the hosted
runners here only run the test suite.

Safety of a public repository with self-hosted runners: collection jobs start only through `workflow_dispatch`,
which needs write access, so a pull request from a fork can never run code on a maintainer's machine. Pull
requests run the tests on GitHub-hosted runners only. Runners take their data paths from their own local
environment, never from the repository.

## What it does not do

It does not get around bot protection, log in anywhere, or publish collected data. It reads what Common Crawl
and the Internet Archive already hold, and it identifies itself with its user agent.
