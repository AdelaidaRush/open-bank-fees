"""Facts a rule can prove, each carried with the exact line it came from.

No field is inferred. A sentence has to contain both the thing (a monthly fee, an outgoing wire) and its
value (a price, a count, a number of days) for a fact to be written, and the line travels with it so a
person can find it again. Deciding which account a line belongs to stays with the reader: every fact
records whether its page speaks about business banking ("business") or does not say ("general").
"""
import re

MONEY = r"(?:[$€£]\s?\d[\d,]*(?:\.\d{1,2})?|\d[\d,]*(?:\.\d{1,2})?\s?(?:USD|EUR|GBP|CAD|AUD|CHF|SGD|HKD))"
MONEY_RE = re.compile(MONEY)
PCT_RE = re.compile(r"(?<![\d.])(?:\d{1,2}(?:\.\d{1,3})?|\.\d{1,3})\s?%")
BUSINESS = re.compile(r"(business|commercial|corporate|treasury|merchant|small[-_ ]?business|company accounts?)", re.I)

LABEL = re.compile(r"[A-Z][A-Za-z0-9&/(),.'’ -]{3,80}")
ROW = re.compile(LABEL.pattern + r"\s+" + MONEY + r"(?:\s?(?:each|per item|per month|monthly|per transfer))?")
JUNK = re.compile(r'[{}"\[\]<>]|https?://|\bpx\b')
# Pages that write about banking rather than state this company's own terms. Acorns and Credit Karma
# articles quoted "monthly fees average $13.51" and "Bank of America charges…" as if they were their own.
EDITORIAL_URL = re.compile(r"(/(learn|blog|articles?|news|press|insights?|guides?|resources?|advice|money|"
                           r"academy|education|stories|magazine|library|research|compare|what-is|how-to|faq)(/|-|$)"
                           # a review of someone else's product can sit anywhere in a path: /business/revolut-business-review
                           r"|review|alternative|comparison|versus|[-/]vs[-/]|/best-|/top-\d)", re.I)
EDITORIAL_TEXT = re.compile(r"(for example|on average|averag(e|ing)|most banks|many banks|a lot of banks|some banks|"
                            r"other banks|traditional banks|big banks|industry|survey|study|report(ed)? that|"
                            r"billion|problem|according to|compare|vs\.?\s)", re.I)
FEE_WORD = re.compile(r"(fee|charge|wire|overdraft|stop payment|statement|atm|replacement|return(ed)? item|research|"
                      r"withdrawal|incoming|outgoing|nsf|dormant|inactivity|cashier|money order|coin|currency order)", re.I)
# "Minimum Balance to Earn Disclosed APY $100,000" is a threshold; kept apart so it never reads as a fee
LIMIT_WORD = re.compile(r"(minimum|balance|opening deposit|to open|to avoid|to waive|apy|interest rate|limit)", re.I)
NEAR = 70   # a value must stand within this many characters of its keyword
# A line that talks about waiving or not charging a fee carries a balance or a threshold, not the fee.
# Huntington's "waive the monthly maintenance fee with a balance of at least $50,000" was read as a
# $50,000 monthly fee; "no overdraft fee if overdrawn by $50 or less" as a $50 overdraft fee.
WAIVER_CTX = re.compile(r"(waive[sd]?|avoid|won.t be charged|will not charge|no (overdraft|monthly|maintenance|service)\s+(fee|charge)|"
                        r"(or less|or more|at least|more than|minimum (daily |average )?(ledger |collected )?balance))", re.I)
# An offer is not a price: "free for two years for startups" does not make an account free (NatWest, 14.09).
PROMO = re.compile(r"(promo(tion)? code|promo|bonus|limited[- ]time|special offer|earn \$|cash back|reward|"
                   r"when you open .{0,40} by \w+ \d|offer (ends|expires|valid))", re.I)
# In a waiver line the amount written right before "monthly maintenance fee" is the fee itself:
# "Waive the $20 monthly maintenance fee with any one of the following" states a $20 fee.
FEE_BEFORE = re.compile(r"(" + MONEY + r")\s+monthly\s+(maintenance|service|account)\s+(fee|charge)", re.I)
NOT_BANK_FEE = re.compile(r"(tuition|cost of attendance|salary|income|home price|purchase price|rent\b|loan amount|"
                          r"net worth|room and board|premium|deductible|valuation|revenue|raised)", re.I)

# (field, what the line must say, what value it must carry)
SENTENCE_RULES = [
    ("monthly_fee",        re.compile(r"monthly (service|maintenance|account)?\s*(fee|charge)", re.I), MONEY_RE),
    ("no_monthly_fee",     re.compile(r"\b(no|zero|\$0|without an?)\s+(monthly|maintenance)\s+(service\s+|account\s+)?(fee|charge)", re.I), None),
    ("fee_waiver",         re.compile(r"(waive[sd]?|avoid)\b.{0,80}(minimum|average)\s+(daily\s+)?(ledger\s+|collected\s+)?balance", re.I), MONEY_RE),
    ("min_opening_deposit",re.compile(r"minimum\s+(opening\s+)?deposit|to open\b.{0,40}(deposit|minimum)", re.I), MONEY_RE),
    ("wire_out_domestic",  re.compile(r"(?<!incoming )(?<!inbound )(outgoing|outbound|send(ing)?)\s+(domestic\s+)?wire(?!.{0,30}(international|foreign))|domestic\s+(outgoing|outbound)\s+wire|wire\s+(transfer\s+)?out\b(?!.{0,20}(international|foreign))", re.I), MONEY_RE),
    ("wire_out_intl",      re.compile(r"(outgoing|outbound|send(ing)?)\s+(international|foreign)\s+wire|(international|foreign)\s+(outgoing|outbound)\s+wire|(international|foreign)\s+wire\s+(transfer\s+)?out\b", re.I), MONEY_RE),
    ("wire_in",            re.compile(r"(incoming|inbound|receiv(e|ing))\s+(domestic\s+|international\s+|foreign\s+)?wire", re.I), MONEY_RE),
    ("overdraft_fee",      re.compile(r"overdraft\s+(item\s+)?(fee|charge)|insufficient funds\s+(fee|charge)|\bNSF\b", re.I), MONEY_RE),
    ("fx_markup",          re.compile(r"(exchange|conversion|FX|currency)\s+(rate\s+)?(margin|mark-?up|spread|fee)", re.I), PCT_RE),
    ("onboarding_time",    re.compile(r"open\s+(an?\s+|your\s+)?(business\s+)?account\s+(online\s+)?in\s+(as\s+little\s+as\s+|under\s+|about\s+)?\d{1,3}\s*(minutes?|hours?|days?|business days?)", re.I), None),
    ("currencies_count",   re.compile(r"\b\d{1,3}\+?\s+(currencies|currency accounts)\b", re.I), None),
    ("nonresident",        re.compile(r"(\bnon-?residents?\b|foreign-?owned\s+(business|compan)).{0,80}\b(open|eligib|accept|welcome|apply|available|can(not)?|unable|not able|require)"
                                      r"|\b(open|eligib|accept|welcome|apply|available|can(not)?|unable|not able)\b.{0,80}(\bnon-?residents?\b|foreign-?owned\s+(business|compan))", re.I), None),
    ("prohibited",         re.compile(r"(prohibited|restricted|not (be )?permitted|we (do|will) not (open|bank|accept|serve|support))\b.{0,120}"
                                      r"(gambling|gaming|casino|cannabis|marijuana|crypto|virtual currenc|adult|firearms|weapons|money service|payday|escort)", re.I), None),
    ("crypto_policy",      re.compile(r"(crypto|cryptocurrenc|virtual (currenc|asset)|digital asset|bitcoin|stablecoin)", re.I), None),
]
RAILS = [("ACH", r"\bACH\b"), ("SWIFT", r"\bSWIFT\b"), ("SEPA", r"\bSEPA\b"), ("SEPA Instant", r"SEPA Instant"),
         ("Fedwire", r"\bFedwire\b"), ("RTP", r"\bRTP\b|Real-Time Payments"), ("FedNow", r"\bFedNow\b"),
         ("Faster Payments", r"Faster Payments"), ("CHAPS", r"\bCHAPS\b"), ("BACS", r"\bBACS\b"),
         ("Zelle", r"\bZelle\b"), ("Interac", r"\bInterac\b"), ("PIX", r"\bPIX\b"), ("UPI", r"\bUPI\b")]


def lines(text):
    for raw in text.splitlines():
        l = re.sub(r"[ \t]{3,}", "   ", raw).strip()
        if 6 <= len(l) <= 400:
            yield l


def fee_rows(text, limits=None):
    """Lines of a published fee table: "Outgoing International Wire   $45.00". A label is paired only with a
    price in the same line, never with a price from a neighbouring column. Balance and minimum lines are
    collected into `limits` when a list is passed."""
    out, seen = [], set()
    limits = limits if limits is not None else []
    for l in lines(text):
        cells = [c.strip() for c in l.split("   ") if c.strip()]
        label = None
        for c in cells:
            if ROW.fullmatch(c):
                row, label = c, None
            elif MONEY_RE.fullmatch(c) and label:
                row, label = f"{label} {c}", None
            else:
                label = c if (LABEL.fullmatch(c) and not MONEY_RE.search(c) and len(c.split()) <= 10) else None
                continue
            row = re.sub(r"\s+", " ", row)
            words = [w for w in MONEY_RE.split(row)[0].split() if len(re.sub(r"[^A-Za-z]", "", w)) >= 3]
            if len(words) < 2 or len(row) > 130 or JUNK.search(row) or row.lower() in seen:
                continue
            label_part = MONEY_RE.split(row)[0]
            if NOT_BANK_FEE.search(label_part):
                continue
            if LIMIT_WORD.search(label_part) and not re.search(r"\b(fee|charge)\b", label_part, re.I):
                limits.append(row); continue   # a balance or minimum, not a price
            if not FEE_WORD.search(label_part):
                continue                       # "Midnight Blue $200" is a card tier, not a fee
            seen.add(row.lower()); out.append(row)
    return out[:60]


def _value_near(line, m, value_re):
    """The single value standing next to the keyword. Two different amounts in reach means the line mixes
    a fee with a balance or a limit, and a machine cannot tell which is which: no value is written."""
    window = line[max(0, m.start() - NEAR): m.end() + NEAR]
    vals = list(dict.fromkeys(v.strip() for v in value_re.findall(window)))
    return vals[0] if len(vals) == 1 else None


def facts(text, page_meta):
    """Every fact the rules can prove on one page."""
    url = page_meta["url"]
    if EDITORIAL_URL.search(url):
        return []
    scope = "business" if BUSINESS.search(url + " " + (page_meta.get("title") or "")) else "general"
    base = {k: page_meta.get(k) for k in ("url", "crawl", "captured", "sha1")}
    out = []
    limit_rows = []
    for row in fee_rows(text, limit_rows):
        out.append({**base, "field": "fee_row", "quote": row, "value": MONEY_RE.findall(row)[-1], "scope": scope, "method": "code"})
    for row in limit_rows:
        out.append({**base, "field": "balance_row", "quote": row, "value": MONEY_RE.findall(row)[-1], "scope": scope, "method": "code"})
    for l in lines(text):
        if JUNK.search(l) or EDITORIAL_TEXT.search(l):
            continue
        for field, thing, value_re in SENTENCE_RULES:
            if field == "crypto_policy":
                continue                       # handled below with a stricter test
            m = thing.search(l)
            if not m:
                continue
            if NOT_BANK_FEE.search(l) or PROMO.search(l):
                continue
            if field == "fx_markup" and re.search(r"(up to|reduce|save|cut|lower|less than|assume|for example|e\.g\.|suppose|imagine)\b", l, re.I):
                continue                       # "reduce FX fees by up to 50%" is a claim about savings, not a rate
            if field == "nonresident" and ("?" in l or re.search(r"\btax\b", l, re.I)):
                continue                       # a question in a FAQ or a tax rule is not a stance on opening accounts
            if field == "prohibited" and (re.search(r"UIGEA|Unlawful Internet Gambling Enforcement Act", l, re.I)
                                          or not re.search(r"\b(account|customer|client|business|merchant|user)s?\b", l, re.I)):
                continue                       # the UIGEA notice is boilerplate every US bank prints
            f_name = field
            if field == "monthly_fee" and re.search(r"per\s+(?:[\w.]+\s+){0,3}(merchant|location|terminal|device|user|seat|card|employee)s?\b", l, re.I):
                continue                       # a processor's per-location charge is not an account's monthly fee
            if field == "monthly_fee" and WAIVER_CTX.search(l):
                fb = FEE_BEFORE.search(l)
                if fb:
                    out.append({**base, "field": "monthly_fee", "quote": l[:300], "value": fb.group(1).strip(),
                                "scope": scope, "method": "code"})
            if field in ("monthly_fee", "overdraft_fee") and WAIVER_CTX.search(l):
                # the line states when the fee is not charged; keep the line, never read its amount as the fee
                f_name = "fee_waiver" if field == "monthly_fee" else "overdraft_threshold"
                val = None
            elif field == "currencies_count":
                n = re.search(r"\b(\d{1,3})\+?\s+(currencies|currency accounts)", l, re.I)
                val = n.group(1) + ("+" if "+" in n.group(0) else "") if n else None
            elif value_re is not None:
                val = _value_near(l, m, value_re)
                if val is None and field not in ("fee_waiver", "min_opening_deposit"):
                    continue
            else:
                val = True
            out.append({**base, "field": f_name, "quote": l[:300], "value": val, "scope": scope, "method": "code"})
        # a stance on crypto customers, stated as policy; news headlines and trading copy are not a policy
        if (len(l) <= 240 and re.search(r"(crypto|cryptocurrenc|virtual (currenc|asset)|digital asset)", l, re.I)
                and re.search(r"\b(we|our bank|the bank|accounts?|customers?|clients?|businesses)\b", l, re.I)
                and re.search(r"(prohibit|not (be )?(permitted|allowed|accept|support|open|provide)|do not|does not|will not|"
                              r"cannot|restrict|decline|close|accept|support|offer|allow)", l, re.I)
                and not l.istitle()):
            out.append({**base, "field": "crypto_policy", "quote": l[:300], "value": True, "scope": scope, "method": "code"})
    # a rail named on a page about accounts or pricing; a passing mention elsewhere proves nothing
    if scope == "business" or re.search(r"(pricing|fees?|account|payments?|transfers?|wires?)", url, re.I):
        rails = sorted({name for name, rx in RAILS if re.search(rx, text)})
        if rails:
            out.append({**base, "field": "rails", "value": rails, "quote": None, "scope": scope, "method": "code"})
    seen, uniq = set(), []
    for f in out:
        # the same line repeated on a page (tabs, mobile copies) is one fact
        k = (f["field"], re.sub(r"\W+", " ", (f["quote"] or "")).strip().lower(), str(f["value"]))
        if k not in seen:
            seen.add(k); uniq.append(f)
    return uniq
