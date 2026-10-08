import numpy as np
import pandas as pd
import pytest

from congress.paper import Rules, benchmark_curve, fill_index, simulate, summarize


def closes(n=60, **cols):
    idx = pd.bdate_range("2026-01-05", periods=n)
    return pd.DataFrame({k: np.full(n, v, dtype=float) if np.isscalar(v) else np.asarray(v, dtype=float)
                         for k, v in cols.items()}, index=idx)


def dec(i, sym, date, action="buy", priority=0):
    return {"id": i, "symbol": sym, "ticker": sym, "action": action, "data_date": date, "priority": priority}


def test_fill_is_strictly_after_the_data_date():
    cal = closes(10, A=1).index
    d = cal[3]
    assert fill_index(cal, d) == 4                    # decided on day 3's close -> fills on day 4's close
    assert fill_index(cal, cal[-1]) is None           # next close hasn't happened yet


def test_buy_fills_at_next_close_with_slippage_and_never_same_day():
    px = closes(30, A=[100] * 3 + [110] * 27)         # jumps on day 3
    d0 = px.index[2]                                  # decision uses the close of day 2 (price 100)
    r = simulate([dec("a", "A", d0)], px, Rules(slippage=0.01, hold_days=100))
    pos = r["positions"][0]
    assert pos["entry_date"] == px.index[3].strftime("%Y-%m-%d")
    assert pos["entry_price"] == pytest.approx(110 * 1.01)      # day 3's close, plus slippage
    assert r["outcomes"]["a"]["status"] == "filled"


def test_decision_on_the_last_day_stays_pending():
    px = closes(10, A=100)
    r = simulate([dec("a", "A", px.index[-1])], px)
    assert r["outcomes"]["a"]["status"] == "pending" and not r["positions"]


def test_time_exit_closes_at_that_days_close():
    prices = [100.0] * 5 + [100.0 + k for k in range(1, 56)]
    px = closes(60, A=prices)
    r = simulate([dec("a", "A", px.index[1])], px, Rules(hold_days=10, slippage=0))
    c = r["closed"][0]
    assert c["reason"] == "time" and c["days_held"] == 10
    assert c["entry_date"] == px.index[2].strftime("%Y-%m-%d") and c["exit_date"] == px.index[12].strftime("%Y-%m-%d")
    assert c["pnl"] == pytest.approx(100 * (prices[12] / prices[2] - 1))


def test_slots_and_cash_limit_buys_and_report_why():
    px = closes(20, **{f"S{k}": 10 for k in range(5)})
    ds = [dec(f"d{k}", f"S{k}", px.index[1], priority=10 - k) for k in range(5)]
    r = simulate(ds, px, Rules(max_positions=3))
    assert [o["status"] for o in (r["outcomes"][f"d{k}"] for k in range(5))] == ["filled"] * 3 + ["skipped"] * 2
    assert "slots" in r["outcomes"]["d3"]["note"]
    r2 = simulate(ds, px, Rules(start_cash=250, max_positions=10))
    assert sum(o["status"] == "filled" for o in r2["outcomes"].values()) == 2
    assert "cash" in r2["outcomes"]["d2"]["note"]


def test_sell_closes_a_held_position_and_is_a_noop_otherwise():
    px = closes(30, A=[100] * 10 + [120] * 20, B=50)
    r = simulate([dec("buy", "A", px.index[1]), dec("sellA", "A", px.index[12], "sell"),
                  dec("sellB", "B", px.index[12], "sell")], px, Rules(slippage=0))
    assert r["closed"][0]["reason"] == "sell signal" and r["closed"][0]["pnl"] == pytest.approx(20.0)
    assert r["outcomes"]["sellB"]["status"] == "skipped" and not r["positions"]


def test_equity_starts_flat_and_marks_open_positions():
    px = closes(30, A=[100] * 6 + [100 + 5 * k for k in range(24)])
    r = simulate([dec("a", "A", px.index[3])], px, Rules(slippage=0, hold_days=100))
    assert r["equity"][0]["value"] == pytest.approx(1000.0)
    last = r["equity"][-1]["value"]
    assert last == pytest.approx(900 + 100 * px["A"].iloc[-1] / 100)
    assert summarize(r, 1000.0)["return"] == pytest.approx(last / 1000 - 1)


def test_benchmark_buys_at_the_first_close_after_start():
    px = closes(10, SPY=[100, 100, 100, 110, 121, 121, 121, 121, 121, 121])
    c = benchmark_curve(px, "SPY", px.index[2], 1000.0)
    assert c[0]["value"] == pytest.approx(1000.0) and c[1]["value"] == pytest.approx(1100.0)
    assert c[-1]["value"] == pytest.approx(1100.0)       # bought at 110, ends at 121


# --- price refresh must never shrink a history -------------------------------------------
def _series(start, n, base=100.0, step=1.0):
    idx = pd.bdate_range(start, periods=n)
    return pd.Series(base + step * np.arange(n), index=idx)


def test_a_full_redownload_replaces_the_history():
    from congress.prices import merge_history
    old = _series("2020-01-01", 100)
    new = old * 0.98                                        # same days, re-based for a dividend
    pd.testing.assert_series_equal(merge_history(old, new), new)


def test_a_truncated_download_never_replaces_a_longer_history():
    from congress.prices import merge_history
    old = _series("2013-01-02", 3000)
    new = old.iloc[-8:] * 1.0                               # Yahoo returned only the last 8 days (the ET bug)
    out = merge_history(old, new)
    assert len(out) == 3000 and out.index.min() == old.index.min()


def test_a_truncated_download_still_adds_newer_days_on_the_old_basis():
    from congress.prices import merge_history
    old = _series("2024-01-01", 200)
    newer = pd.Series([old.iloc[-1] * 0.5 * 1.01, old.iloc[-1] * 0.5 * 1.02],
                      index=pd.bdate_range(old.index[-1] + pd.offsets.BDay(1), periods=2))
    new = pd.concat([pd.Series([old.iloc[-1] * 0.5], index=[old.index[-1]]), newer])   # different basis (x0.5)
    out = merge_history(old, new)
    assert len(out) == 202 and out.iloc[-2] == pytest.approx(old.iloc[-1] * 1.01)      # rescaled to the old basis
    assert out.loc[old.index].equals(old)                                              # old days untouched


def test_nothing_to_anchor_on_leaves_the_old_history_alone():
    from congress.prices import merge_history
    old = _series("2020-01-01", 50)
    new = _series("2021-06-01", 5)
    assert merge_history(old, new).equals(old)
