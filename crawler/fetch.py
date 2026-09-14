"""Pull one record out of a Common Crawl WARC file with a range request and turn it into text."""
import gzip, re, shutil, subprocess, tempfile, time, urllib.request
from lxml import html as LH
from . import config

PDFTOTEXT = shutil.which("pdftotext")


def warc_payload(rec, tries=4):
    off, ln = int(rec["offset"]), int(rec["length"])
    url = config.CC_DATA + rec["filename"]
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"Range": f"bytes={off}-{off + ln - 1}", "User-Agent": config.UA})
            raw = urllib.request.urlopen(req, timeout=120).read()
            warc = gzip.decompress(raw)
            parts = warc.split(b"\r\n\r\n", 2)          # WARC header, HTTP header, body
            return parts[2] if len(parts) == 3 else b""
        except Exception:
            time.sleep(2 * (attempt + 1))
    return None


def html_text(body):
    """Visible text, one block per line. Tables keep cells apart with three spaces, so a fee label and its
    price stay on one line and a label is never glued to a price from the next column."""
    try:
        doc = LH.fromstring(body)
    except Exception:
        return "", ""
    for bad in doc.xpath("//script|//style|//noscript|//svg|//nav|//footer|//header|//form"):
        bad.drop_tree()
    title = " ".join(doc.xpath("//title//text()")).strip()
    lines = []
    for tr in doc.xpath("//tr"):
        cells = [re.sub(r"\s+", " ", c.text_content()).strip() for c in tr.xpath("./th|./td")]
        cells = [c for c in cells if c]
        if cells:
            lines.append("   ".join(cells))
        tr.drop_tree()
    for el in doc.xpath("//h1|//h2|//h3|//h4|//p|//li|//dt|//dd|//div[not(*)]|//span[not(*)]"):
        t = re.sub(r"\s+", " ", el.text_content()).strip()
        if len(t) > 2:
            lines.append(t)
    seen, out = set(), []
    for l in lines:
        if l not in seen:
            seen.add(l); out.append(l)
    return title, "\n".join(out)


def pdf_text(body):
    if not PDFTOTEXT or not body.startswith(b"%PDF"):
        return ""
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(body); f.flush()
        r = subprocess.run([PDFTOTEXT, "-layout", "-q", f.name, "-"], capture_output=True, timeout=90)
        return r.stdout.decode("utf-8", "ignore")


def to_text(rec):
    body = warc_payload(rec)
    if body is None:
        return None
    if len(body) > config.MAX_BYTES:
        body = body[:config.MAX_BYTES]
    mime = rec.get("mime", "")
    if "pdf" in mime or body[:4] == b"%PDF":
        return {"kind": "pdf", "title": rec["url"].rsplit("/", 1)[-1], "text": pdf_text(body), "bytes": len(body)}
    title, text = html_text(body)
    return {"kind": "html", "title": title, "text": text, "bytes": len(body)}
