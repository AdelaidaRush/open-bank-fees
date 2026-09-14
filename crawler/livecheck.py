"""Second source for every archived fact: open the same address on the live site and look for the same line.

An archived page proves the bank published a line on the capture date. It does not prove the bank still
says it. A fact is "confirmed live" only when the line is found again on today's page; "not on live page"
and "live page unreachable" are recorded as they are, and never counted as confirmed.
"""
import json, random, re, shutil, subprocess, sys, tempfile, time, urllib.request
from . import config, fetch, verify

UA = {"User-Agent": config.UA}


def live_text(url):
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read(config.MAX_BYTES)
            ct = r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return None, f"http {e.code}"
    except Exception as e:
        return None, type(e).__name__
    if "pdf" in ct or body[:4] == b"%PDF":
        return fetch.pdf_text(body), "ok"
    return fetch.html_text(body)[1], "ok"


def check(facts, pause=1.0):
    out = []
    for f in facts:
        text, st = live_text(f["url"])
        if text is None:
            verdict = "live page unreachable"
        elif verify.check(f, text):
            verdict = "confirmed live"
        else:
            verdict = "not on live page"
        out.append({**f, "live": verdict, "live_status": st})
        time.sleep(pause)
    return out
