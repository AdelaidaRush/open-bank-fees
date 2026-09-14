"""open-bank-fees: finds banks' published fees and terms in open web archives.

It reads Common Crawl and the Wayback Machine, not the banks' own servers, keeps the text of every page
it used, and writes each fact together with the exact sentence it came from. A fact whose sentence
cannot be found again in the stored page is rejected.
"""
__version__ = "0.1.0"
