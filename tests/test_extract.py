from crawler import extract, verify

SCHEDULE = """Business Checking Fee Schedule
Monthly Maintenance Fee   $15.00
Outgoing International Wire   $45.00
Incoming Wire   $15.00
Overdraft Item Fee   $34.00
Domestic   $10
The monthly maintenance fee is waived with a minimum daily balance of $2,500.
We support ACH and SWIFT payments."""


def test_fee_rows_pair_label_and_price_on_one_line():
    rows = extract.fee_rows(SCHEDULE)
    assert "Outgoing International Wire $45.00" in rows
    assert not any(r.startswith("Domestic") for r in rows), "a one-word label says nothing on its own"


def test_facts_carry_their_line_and_verify():
    meta = {"url": "https://bank.example/business-fee-schedule.pdf", "title": "", "sha1": "x"}
    facts = extract.facts(SCHEDULE, meta)
    fields = {f["field"] for f in facts}
    assert {"fee_row", "monthly_fee", "wire_out_intl", "wire_in", "overdraft_fee", "fee_waiver", "rails"} <= fields
    assert all(f["scope"] == "business" for f in facts)
    assert all(verify.check(f, SCHEDULE) for f in facts)


def test_a_line_not_in_the_page_is_rejected():
    fake = {"field": "monthly_fee", "quote": "Monthly fee $0", "value": "$0"}
    assert not verify.check(fake, SCHEDULE)


def test_waiver_balance_is_never_read_as_the_fee():
    line = "We'll waive the monthly maintenance fee with a business deposit relationship balance of at least $50,000."
    f = [x for x in extract.facts(line, {"url": "https://b.example/business-checking", "title": "", "sha1": "x"})]
    assert not any(x["field"] == "monthly_fee" for x in f)
    assert any(x["field"] == "fee_waiver" and x["value"] is None for x in f)


def test_overdraft_threshold_is_not_the_overdraft_fee():
    line = "If you overdraw your account by $50 or less, you won't be charged an overdraft fee."
    f = extract.facts(line, {"url": "https://b.example/checking", "title": "", "sha1": "x"})
    assert not any(x["field"] == "overdraft_fee" for x in f)


def test_blog_pages_and_other_banks_are_skipped():
    line = "For example, Bank of America charges a monthly maintenance fee of $12."
    assert extract.facts(line, {"url": "https://acorns.example/learn/checking", "title": "", "sha1": "x"}) == []
    assert not extract.facts(line, {"url": "https://acorns.example/checking", "title": "", "sha1": "x"})


def test_student_costs_are_not_bank_fees():
    assert extract.fee_rows("Tuition & Fees   $54,844") == []


def test_small_percent_keeps_its_dot():
    f = extract.facts("Currency Conversion Fee   .20% of the transaction amount", {"url": "https://b.example/fees", "title": "", "sha1": "x"})
    assert any(x["field"] == "fx_markup" and x["value"].startswith(".20") for x in f)


def test_fee_named_before_monthly_fee_in_a_waiver_line_is_the_fee():
    f = extract.facts("Waive the $20 monthly maintenance fee with any one of the following:",
                      {"url": "https://b.example/business-checking", "title": "", "sha1": "x"})
    assert any(x["field"] == "monthly_fee" and x["value"] == "$20" for x in f)


def test_a_promotion_is_not_a_price():
    f = extract.facts("Promo code Q3DIG26 must be used when opening an account with a minimum deposit of $25.",
                      {"url": "https://b.example/business-checking", "title": "", "sha1": "x"})
    assert not any(x["field"] == "min_opening_deposit" for x in f)


def test_a_review_of_another_company_is_skipped():
    assert extract.facts("No monthly fees", {"url": "https://transfergo.example/business/revolut-business-review", "title": "", "sha1": "x"}) == []


def test_savings_claim_is_not_an_fx_markup():
    f = extract.facts("Reduce account management and FX fees by up to 50% with a business account.",
                      {"url": "https://yapeal.example/business", "title": "", "sha1": "x"})
    assert not any(x["field"] == "fx_markup" for x in f)


def test_uigea_boilerplate_is_not_a_policy():
    f = extract.facts("Restricted Transactions. The Unlawful Internet Gambling Enforcement Act of 2006 prohibits gambling businesses.",
                      {"url": "https://b.example/business-account-agreement", "title": "", "sha1": "x"})
    assert not any(x["field"] == "prohibited" for x in f)


def test_nonresident_needs_a_stance():
    meta = {"url": "https://b.example/business", "title": "", "sha1": "x"}
    assert not any(x["field"] == "nonresident" for x in extract.facts("Where the Customer is a non-resident, the Bank may apply a reduced tax rate.", meta))
    assert any(x["field"] == "nonresident" for x in extract.facts("Non-resident founders can open a business account online.", meta))


def test_incoming_wire_is_never_filed_as_outgoing():
    f = extract.facts("$0 for incoming domestic wires from anywhere in the USA", {"url": "https://b.example/business-fees", "title": "", "sha1": "x"})
    assert not any(x["field"] in ("wire_out_domestic", "wire_out_intl") for x in f)


def test_balance_threshold_is_a_limit_not_a_fee():
    rows_lim = []
    fees = extract.fee_rows("Minimum Balance to Earn Disclosed APY   $100,000", rows_lim)
    assert fees == [] and rows_lim


def test_worked_example_is_not_an_fx_markup():
    f = extract.facts("Assume the exchange rate is 1.3176. After adding our 0.5% currency conversion fee you pay more.",
                      {"url": "https://b.example/fees", "title": "", "sha1": "x"})
    assert not any(x["field"] == "fx_markup" for x in f)


def test_per_location_charge_is_not_a_monthly_account_fee():
    f = extract.facts("This is a fixed monthly fee of $1.25 per active U.S. merchant location.", {"url": "https://p.example/pricing", "title": "", "sha1": "x"})
    assert not any(x["field"] == "monthly_fee" for x in f)
