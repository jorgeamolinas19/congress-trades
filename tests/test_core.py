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
