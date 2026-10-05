import numpy as np
import pandas as pd
import pytest

from congress import analysis, metrics
from congress.clean import parse_amount
from congress.portfolio import Rules, build_positions, run
from congress.scrape_house import parse_ptr_text


# ----------------------------------------------------------------- parsing --
@pytest.mark.parametrize("raw, expected", [
    ("$1,001 - $15,000", (1001, 15000)),
    ("$1,000,001 - $5,000,000", (1_000_001, 5_000_000)),
    ("Over $50,000,000", (50_000_000, 50_000_000)),
    ("$165.29", (165.29, 165.29)),
    ("$15,001 -", (15001, 50000)),  # upper half lost to a line wrap
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


def test_parse_amount_missing():
    lo, hi = parse_amount(None)
    assert np.isnan(lo) and np.isnan(hi)


HOUSE_MODERN = """ID Owner Asset Transaction Date Notification Amount Cap.
SP Albemarle Corporation (ALB) [ST] S 12/21/2023 01/08/2024 $1,001 - $15,000
F S: New
SP Charles Schwab Corporation (SCHW) P 12/14/2023 01/08/2024 $50,001 -
[ST] $100,000
F S: Amended
"""

HOUSE_GARBLED = """iD owner asset transaction Date notification amount cap.
sP Air Products and Chemicals, Inc. S (partial) 06/04/2019 06/12/2019 $1,001 - $15,000 gfedc
(aPD) [sT]
FILINg STATuS: New
JT american Express Company (aXP) S 01/27/2016 02/16/2016 $1,001 - $15,000
FILINg STaTUS: New
"""


def test_house_parser_wrapped_amount_and_tag():
    rows = parse_ptr_text(HOUSE_MODERN)
    assert [r["ticker"] for r in rows] == ["ALB", "SCHW"]
    assert rows[1]["amount"] == "$50,001 - $100,000"
    assert rows[1]["asset_code"] == "ST"
    assert rows[0]["owner"] == "SP" and rows[1]["type"] == "P"


def test_house_parser_garbled_case_and_partial():
    rows = parse_ptr_text(HOUSE_GARBLED)
    assert [r["ticker"] for r in rows] == ["APD", "AXP"]  # never "PARTIAL"
    assert rows[0]["type"] == "S (partial)"
    assert rows[0]["owner"] == "SP" and rows[1]["owner"] == "JT"


# ----------------------------------------------------------- portfolios --
@pytest.fixture
def toy():
    cal = pd.bdate_range("2020-01-01", periods=30)
    rets = pd.DataFrame({"AAA": 0.0, "BBB": 0.0}, index=cal)
    rets.loc[cal[5], "AAA"] = 0.10    # jump on day 5 = the filing date
    rets.loc[cal[2], "BBB"] = 0.20    # jump on day 2, right after the trade
    buys = pd.DataFrame({
        "member": ["m1", "m2"], "symbol": ["AAA", "BBB"],
        "tx_date": [cal[1], cal[1]], "filing_date": [cal[5], cal[5]],
        "amount_mid": [10_000.0, 30_000.0],
    })
    return cal, rets, buys


def test_filing_date_portfolio_has_no_lookahead(toy):
    cal, rets, buys = toy
    port, _ = run(buys, rets, Rules.filing_date(hold_days=10))
    # Entry is at the close of filing day + 1, so neither the filing-day jump
    # nor the earlier post-trade jump may appear in the investable returns.
    assert port.ret.fillna(0).abs().max() == 0


def test_trade_date_portfolio_captures_post_trade_move(toy):
    cal, rets, buys = toy
    port, _ = run(buys, rets, Rules.trade_date(hold_days=10))
    # Day 2: both positions open, equal weight -> (0 + 0.20) / 2
    assert port.ret.loc[cal[2]] == pytest.approx(0.10)
    # Trade-date close is the entry, so the trade-day return itself is excluded.
    assert np.isnan(port.ret.loc[cal[1]])


def test_dollar_weighting(toy):
    cal, rets, buys = toy
    port, _ = run(buys, rets, Rules.trade_date(hold_days=10, weight="amount_mid"))
    assert port.ret.loc[cal[2]] == pytest.approx(0.20 * 30 / 40)


def test_hold_period_length(toy):
    cal, rets, buys = toy
    port, W = run(buys.iloc[:1], rets, Rules.trade_date(hold_days=7))
    held = W["AAA"] > 0
    assert held.sum() == 7 and held.idxmax() == cal[2]


def test_exit_on_sale_uses_only_known_information(toy):
    cal, rets, buys = toy
    sells = pd.DataFrame({"member": ["m1"], "symbol": ["AAA"],
                          "tx_date": [cal[8]], "filing_date": [cal[20]]})
    pos = build_positions(buys.iloc[:1], cal, Rules.filing_date(hold_days=126, exit_on_sale=True), sells)
    # The copier learns of the sale on the filing date and exits a day later.
    assert pos.exit_i.iloc[0] == 21


# --------------------------------------------------------------- analysis --
def test_factor_regression_recovers_alpha():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2015-01-01", periods=2500)
    f = pd.DataFrame(rng.normal(0, 0.01, (len(idx), 6)), index=idx,
                     columns=["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"])
    f["RF"] = 0.0001
    true_alpha = 0.10 / 252
    r = f.RF + true_alpha + 1.2 * f["Mkt-RF"] + 0.5 * f["Mom"] + rng.normal(0, 0.002, len(idx))
    out = analysis.factor_regression(r, f, "FF5+Mom")
    assert out["alpha_ann"] == pytest.approx(0.10, abs=0.02)
    assert out["b_Mkt-RF"] == pytest.approx(1.2, abs=0.02)
    assert out["alpha_t"] > 5


def test_delay_car_sums_returns_between_trade_and_copier_entry():
    cal = pd.bdate_range("2020-01-01", periods=10)
    ar = pd.DataFrame({"X": np.arange(10) / 100.0}, index=cal)
    ev = pd.DataFrame({"symbol": ["X"], "tx_date": [cal[2]], "filing_date": [cal[5]]})
    # Days 3..6 inclusive (entry is the close of filing day + 1).
    assert analysis.delay_car(ev, ar).iloc[0] == pytest.approx((3 + 4 + 5 + 6) / 100)


def test_holm_is_monotone_and_capped():
    p = pd.Series({"a": 0.01, "b": 0.04, "c": 0.03, "d": 0.5})
    adj = analysis.holm(p)
    assert adj["a"] == pytest.approx(0.04)
    assert adj["c"] == pytest.approx(0.09) and adj["b"] == pytest.approx(0.09)
    assert adj.max() <= 1


def test_max_drawdown():
    r = pd.Series([0.10, -0.50, 0.20])
    assert metrics.max_drawdown(r) == pytest.approx(-0.50)


def test_house_asset_text_stops_at_filing_status():
    text = """CME group Inc. Class A (CME) P 01/02/2018 01/20/2018 $1,001 - $15,000
FILINg STATUS: New
SUBHoLDINg oF: Stocks, Bonds, & Mutual Funds
"""
    row = parse_ptr_text(text)[0]
    assert row["ticker"] == "CME"
    assert "Bonds" not in row["asset"]


@pytest.mark.parametrize("name, is_stock", [
    ("Apple Inc. (AAPL)", True),
    ("Callaway Golf Company", True),
    ("Putnam Bancorp", True),
    ("SPDR S&P 500 ETF Trust", False),
    ("NVDA call option exp 1/17/2025", False),
    ("US Treasury Note 2.5% 2030", False),
    ("Vanguard Total Stock Market Index Fund", False),
])
def test_non_stock_filter(name, is_stock):
    from congress.clean import NON_STOCK_WORDS
    assert (NON_STOCK_WORDS.search(name) is None) == is_stock


@pytest.mark.parametrize("text, kind, strike, expiry", [
    ("SPDR S&P 500 ETF Option Type: Put Strike price: $210.00 Expires: 06/30/2017", "Put", 210.0, "06/30/2017"),
    ("Purchase of 50 call options with a strike price of $22 and an expiration date of 1/15/16", "Call", 22.0, "1/15/16"),
    ("CALL ISHARES RUSSELL 2000 $175 EXP 09/19/25", "Call", 175.0, "09/19/25"),
    ("Call Option, $180, Exp. 4/5/19", "Call", 180.0, "4/5/19"),
    ("SPY Feb 2016 put 180.000", "Put", 180.0, "Feb 2016"),   # year must not become the strike
    ("TLT MaY 17 124.5 CaLL", "Call", 124.5, None),
])
def test_option_detail(text, kind, strike, expiry):
    from congress.other_assets import option_detail
    d = option_detail(text)
    assert (d["option_type"], d["strike"], d["expiry"]) == (kind, strike, expiry)


@pytest.mark.parametrize("code, text, expected", [
    ("OP", "Apple Inc. (AAPL)", "Options"),
    ("Municipal Security", "Univ Ala Gen Fee Rev Ref-A Bond", "Bonds & Treasuries"),
    (None, "US Treasury Note 2.5% 2030", "Bonds & Treasuries"),
    (None, "SPDR S&P 500 ETF Trust", "Funds & ETFs"),
    (None, "Purchase of 92 call options", "Options"),
    ("CT", "Bitcoin", "Crypto"),
])
def test_classify(code, text, expected):
    from congress.other_assets import classify
    assert classify(code, text) == expected


def test_parse_amount_rejects_upper_bound_below_lower():
    # "Cap. Gains > $200?" header text captured as the upper bound
    assert parse_amount("$15,001 - $200") == (15001, 50000)


def test_house_parser_wrapped_amount_skips_cap_gains_header():
    text = """SP Tempus AI, Inc. (TEM) [OP] P 01/16/2026 01/23/2026 $50,001 -
Cap. Gains > $200?
$100,000
F S: New
"""
    assert parse_ptr_text(text)[0]["amount"] == "$50,001 - $100,000"


def test_shrinkage_pulls_lucky_small_records_to_the_mean():
    from congress.odds import member_odds, shrinkage_strength
    rng = np.random.default_rng(1)
    n = rng.integers(10, 200, 150).astype(float)
    rates = rng.binomial(n.astype(int), 0.5) / n      # everyone is a coin flip
    k = shrinkage_strength(rates, n, 0.25)
    assert k > 100                                    # no real dispersion -> strong prior
    lucky = member_odds(rate=10 / 12, n=12, p=0.5, k=k, unit_var=0.25)
    assert 0.45 < lucky["odds"] < 0.56


def test_shrinkage_trusts_real_dispersion():
    from congress.odds import shrinkage_strength
    rng = np.random.default_rng(2)
    n = np.full(150, 400.0)
    skill = rng.choice([0.3, 0.7], 150)               # members genuinely differ
    k = shrinkage_strength(rng.binomial(400, skill) / n, n, 0.21)
    assert k < 20


def test_filing_scores_count_each_filing_once():
    from congress.odds import filing_scores
    per, _ = filing_scores(pd.Series(["a"] * 4), pd.Series([1, 1, 1, 2]), pd.Series([1, 1, 1, 0]))
    assert per.loc["a", "n"] == 2 and per.loc["a", "rate"] == pytest.approx(0.5)


def test_outcome_stats_percentiles_and_ci():
    from congress.odds import outcome_stats
    ret = pd.Series(np.linspace(-0.5, 0.5, 101))
    out = outcome_stats(ret, ret, pd.Series(np.arange(101) % 10))
    assert out["n"] == 101 and out["return_percentiles"]["p50"] == pytest.approx(0.0)
    assert out["hit_ci"][0] < out["hit_rate"] < out["hit_ci"][1]
