"""Run the full study on data/processed/trades.parquet and write all results.

    python -m congress.study

Outputs go to reports/results/ (tables) and reports/results/headline.json.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import analysis, metrics, prices, sectors
from .config import PROCESSED, REPORTS
from .factors import load_factors
from .portfolio import Rules, run

OUT = REPORTS / "results"
OUT.mkdir(parents=True, exist_ok=True)
MIN_NAMES = 20       # evaluation starts once both portfolios hold this many names
HEADLINE_MODEL = "FF5+Mom"


def load_inputs():
    trades = pd.read_parquet(PROCESSED / "trades.parquet")
    factors = load_factors()
    rets = prices.load_returns()
    rets = rets.loc[rets.index.isin(factors.index)]           # common trading calendar
    rets = rets.where(rets < 2.0)                               # >200% one-day moves are bad ticks
    spy = rets.pop("SPY")
    return trades, factors, rets, spy


def _window(*ports: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    ok = pd.concat([p.n_names >= MIN_NAMES for p in ports], axis=1).all(axis=1)
    return ok.idxmax(), ok[ok].index.max()


def describe_sample(trades: pd.DataFrame) -> dict:
    buys = trades[trades.side == "buy"]
    by_member = buys.groupby("member").size().sort_values(ascending=False)
    return {
        "n_trades": int(len(trades)), "n_buys": int(len(buys)), "n_sells": int((trades.side == "sell").sum()),
        "n_members": int(trades.member.nunique()), "n_tickers": int(trades.ticker.nunique()),
        "first_trade": str(trades.tx_date.min().date()), "last_trade": str(trades.tx_date.max().date()),
        "median_delay_days": float(trades.delay_days.median()),
        "pct_filed_late_over_45d": float((trades.delay_days > 45).mean()),
        "top10_members_share_of_buys": float(by_member.head(10).sum() / len(buys)),
        "top_members": by_member.head(10).to_dict(),
        "buys_by_chamber": buys.chamber.value_counts().to_dict(),
        "buys_by_party": buys.party.value_counts().to_dict(),
    }


def headline_portfolios(buys, sells, rets):
    out = {}
    for name, rules in {"trade_date": Rules.trade_date(), "filing_date": Rules.filing_date()}.items():
        out[name] = run(buys, rets, rules, sells)
    return out


def robustness_specs(buys: pd.DataFrame, sells: pd.DataFrame, top5: list[str], tech: set[str]):
    """(label, group, buys subset, rule overrides, sells) for every robustness slice."""
    b = buys
    specs = [
        ("House only", "chamber", b[b.chamber == "House"], {}),
        ("Senate only", "chamber", b[b.chamber == "Senate"], {}),
        ("Democrats", "party", b[b.party == "Democrat"], {}),
        ("Republicans", "party", b[b.party == "Republican"], {}),
        ("Member / joint accounts", "owner", b[b.owner.isin(["Self", "Joint"])], {}),
        ("Spouse / child accounts", "owner", b[b.owner.isin(["Spouse", "Child"])], {}),
        ("Trades >= $15k", "size", b[b.amount_low >= 15_001], {}),
        ("Excluding top-5 names", "concentration", b[~b.symbol.isin(top5)], {}),
        ("Excluding NVDA", "concentration", b[b.symbol != "NVDA"], {}),
        ("Excluding Technology sector", "concentration", b[~b.symbol.isin(tech)], {}),
        ("Dollar-weighted (low end)", "weighting", b, {"weight": "amount_low"}),
        ("Dollar-weighted (midpoint)", "weighting", b, {"weight": "amount_mid"}),
        ("Dollar-weighted (high end)", "weighting", b, {"weight": "amount_high"}),
        ("Hold 1 month", "holding", b, {"hold_days": 21}),
        ("Hold 3 months", "holding", b, {"hold_days": 63}),
        ("Hold 12 months", "holding", b, {"hold_days": 252}),
        ("Exit when member's sale is known", "holding", b, {"exit_on_sale": True, "hold_days": 252}),
    ]
    return specs


def main() -> dict:
    trades, factors, rets, spy = load_inputs()
    trades = trades[trades.symbol.isin(rets.columns)]
    buys = trades[trades.side == "buy"].copy()
    sells = trades[trades.side == "sell"].copy()
    rf = factors.RF
    res: dict = {"sample": describe_sample(trades)}

    # ---- 1. Headline portfolios -------------------------------------------
    ports = headline_portfolios(buys, sells, rets)
    sell_port, _ = run(sells, rets, Rules.filing_date())
    start, end = _window(*(p for p, _ in ports.values()))
    res["window"] = {"start": str(start.date()), "end": str(end.date())}
    sl = slice(start, end)
    series = pd.DataFrame({k: p.ret for k, (p, _) in ports.items()}).loc[sl]
    series["spy"] = spy.loc[sl]
    series["sells_filing_date"] = sell_port.ret.loc[sl]
    series["delay_cost"] = series.trade_date - series.filing_date
    series["buys_minus_sells"] = series.filing_date - series.sells_filing_date
    series.join(pd.DataFrame({f"n_{k}": p.n_names for k, (p, _) in ports.items()})).to_csv(OUT / "daily_returns.csv")

    summ = {k: metrics.summary(series[k], series.spy, rf) for k in ["trade_date", "filing_date", "spy", "sells_filing_date"]}
    pd.DataFrame(summ).T.to_csv(OUT / "summary_metrics.csv")
    res["summary"] = summ

    # ---- 2. Factor regressions --------------------------------------------
    regs = []
    for k in ["trade_date", "filing_date", "sells_filing_date"]:
        for m in analysis.MODELS:
            regs.append({"portfolio": k, **analysis.factor_regression(series[k], factors, m)})
    for k in ["delay_cost", "buys_minus_sells"]:
        for m in analysis.MODELS:
            regs.append({"portfolio": k, **analysis.factor_regression(series[k], factors, m, excess=False)})
    regs = pd.DataFrame(regs)
    regs.to_csv(OUT / "factor_regressions.csv", index=False)
    res["regressions"] = regs[regs.model.isin(["CAPM", HEADLINE_MODEL])].to_dict("records")

    # ---- 3. Event study ----------------------------------------------------
    ar = analysis.abnormal_returns(rets, spy)
    ev = buys[(buys.filing_date <= end) & (buys.tx_date >= start - pd.Timedelta(days=60))].copy()
    p_trade = analysis.event_paths(ev, ar, "tx_date", pre=20, post=126)
    p_file = analysis.event_paths(ev, ar, "filing_date", pre=60, post=127)
    month = ev.tx_date.dt.to_period("M")
    ev["car_member_6m"] = analysis.car(p_trade, 1, 126)
    ev["car_delay"] = analysis.delay_car(ev, ar)
    ev["car_copier_6m"] = analysis.car(p_file, 2, 127)
    ev["car_pre_trade_20d"] = analysis.car(p_trade, -20, 0)
    res["event_study"] = {c: analysis.clustered_mean(ev[c], month)
                          for c in ["car_pre_trade_20d", "car_member_6m", "car_delay", "car_copier_6m"]}
    for h in (5, 21, 63):
        res["event_study"][f"car_member_{h}d"] = analysis.clustered_mean(analysis.car(p_trade, 1, h), month)
        res["event_study"][f"car_copier_{h}d"] = analysis.clustered_mean(analysis.car(p_file, 2, h + 1), month)
    # Average-then-cumulate, anchored at each design's entry close (day 0 / day 1).
    for name, paths, anchor in [("trade_date", p_trade, 0), ("filing_date", p_file, 1)]:
        mean_ar = paths.mean()
        pd.DataFrame({"mean_car": mean_ar.cumsum() - mean_ar.loc[:anchor].sum(), "n": paths.notna().sum()}
                     ).to_csv(OUT / f"event_car_{name}.csv", index_label="event_day")
    ev[["member", "chamber", "party", "ticker", "tx_date", "filing_date", "delay_days",
        "car_pre_trade_20d", "car_member_6m", "car_delay", "car_copier_6m"]].to_csv(OUT / "event_level.csv", index=False)

    # ---- 4. Concentration and sectors --------------------------------------
    sector = sectors.load(sorted(set(buys.symbol)))
    conc = {}
    for k, (p, W) in ports.items():
        c = analysis.concentration(W.loc[sl], rets.loc[sl])
        sec_w = c["avg_weight"].groupby(sector.reindex(c["avg_weight"].index).fillna("Unknown")).sum()
        conc[k] = {"avg_top10_weight": c["avg_top_weight"], "avg_names": c["avg_names"],
                   "top_contributors": c["contribution"].head(10).round(4).to_dict(),
                   "top5_share_of_sum_contrib": float(c["contribution"].head(5).sum() / c["contribution"].sum()),
                   "sector_weights": sec_w.sort_values(ascending=False).round(4).to_dict()}
        c["contribution"].to_csv(OUT / f"contribution_{k}.csv", header=["contribution"])
    res["concentration"] = conc

    # ---- 5. Robustness -----------------------------------------------------
    top5 = list(conc["filing_date"]["top_contributors"])[:5]
    tech = set(sector[sector == "Technology"].index)
    rows = []
    for label, group, sub, overrides in robustness_specs(buys, sells, top5, tech):
        for which, base in [("trade_date", Rules.trade_date), ("filing_date", Rules.filing_date)]:
            p, _ = run(sub, rets, base(**overrides), sells)
            r = p.ret.loc[sl]
            fit = analysis.factor_regression(r, factors, HEADLINE_MODEL)
            rows.append({"slice": label, "group": group, "portfolio": which, "n_buys": len(sub),
                         "ann_return": metrics.ann_return(r), "sharpe": metrics.sharpe(r, rf),
                         **{k: fit[k] for k in ["alpha_ann", "alpha_t", "alpha_p", "b_Mkt-RF", "b_Mom"]}})
    for lo, hi in [("2014-01-01", "2017-12-31"), ("2018-01-01", "2021-12-31"), ("2022-01-01", "2026-12-31")]:
        for which in ["trade_date", "filing_date"]:
            r = series[which].loc[lo:hi]
            fit = analysis.factor_regression(r, factors, HEADLINE_MODEL)
            rows.append({"slice": f"Subperiod {lo[:4]}-{min(int(hi[:4]), end.year)}", "group": "subperiod",
                         "portfolio": which, "n_buys": np.nan, "ann_return": metrics.ann_return(r),
                         "sharpe": metrics.sharpe(r, rf),
                         **{k: fit[k] for k in ["alpha_ann", "alpha_t", "alpha_p", "b_Mkt-RF", "b_Mom"]}})
    rob = pd.DataFrame(rows)
    rob["alpha_p_holm"] = rob.groupby("portfolio").alpha_p.transform(analysis.holm)
    rob.to_csv(OUT / "robustness.csv", index=False)
    res["multiple_testing"] = {
        w: {"n_tests": int(len(g)), "n_p_below_05": int((g.alpha_p < 0.05).sum()),
            "n_holm_below_05": int((g.alpha_p_holm < 0.05).sum()),
            "expected_false_positives_at_05": round(0.05 * len(g), 2)}
        for w, g in rob.groupby("portfolio")
    }

    (OUT / "headline.json").write_text(json.dumps(res, indent=2, default=str))
    return res


if __name__ == "__main__":
    r = main()
    print(json.dumps({k: r[k] for k in ["sample", "window", "summary"]}, indent=2, default=str))
    print(pd.read_csv(OUT / "factor_regressions.csv")[["portfolio", "model", "alpha_ann", "alpha_t", "r2"]].to_string(index=False))
    print(json.dumps(r["event_study"], indent=2))
