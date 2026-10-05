"""Export the study's data as static JSON for the website (web/public/data/).

    python -m congress.site_data

Per member, two questions are answered separately:
  * Did their purchases beat the market?  (trade-date portfolio: buy at the
    close of the trade date, hold 6 months, equal weight)
  * Could you have profited by copying them?  (filing-date portfolio: buy the
    day after the disclosure)
"Beat the market" is judged on return vs. SPY over the days the portfolio held
stocks; significance uses the FF5+momentum alpha t-stat with a Holm correction
across all members, because with ~150 members several will clear p < 0.05 by
luck alone.
"""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

from . import analysis, metrics, prices
from .config import PROCESSED, RAW, REPORTS, ROOT
from .factors import load_factors
from .portfolio import Rules, run

OUT = ROOT / "web" / "public" / "data"
MEMBERS_DIR = OUT / "members"
HOLD = 126
MIN_BUYS = 10          # fewer purchases than this: no verdict
MIN_DAYS = 252         # fewer invested days than this: no verdict


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _member_states() -> dict[str, str]:
    out = {}
    for fn in ("legislators-historical.json", "legislators-current.json"):
        for p in json.loads((RAW / fn).read_text(encoding="utf-8")):
            out[p["id"]["bioguide"]] = p["terms"][-1]["state"]
    return out


def _finite(obj):
    """Recursively replace NaN/inf with None: they are not valid JSON."""
    if isinstance(obj, dict):
        return {k: _finite(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_finite(v) for v in obj]
    if isinstance(obj, float) and not np.isfinite(obj):
        return None
    return obj


def _dump(path, obj) -> None:
    path.write_text(json.dumps(_finite(obj), separators=(",", ":"), allow_nan=False))


def _r(x, nd=4):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), nd)


def trade_outcomes(trades: pd.DataFrame, px: pd.DataFrame, spy_px: pd.Series) -> pd.DataFrame:
    """Each trade's stock return vs. SPY over the 6 months after the trade date
    and after the filing (entry the next trading day), compounded. Trades less
    than 6 months old get their return to date, flagged as incomplete."""
    cal = px.index
    col = px.columns.get_indexer(trades.symbol)
    arr = px.to_numpy()
    spy = spy_px.reindex(cal).to_numpy()
    out = {}
    for name, dates, lag in [("trade", trades.tx_date, 0), ("filing", trades.filing_date, 1)]:
        i0 = cal.searchsorted(dates.values, side="left") + lag
        i0 = np.minimum(i0, len(cal) - 1)
        i1 = np.minimum(i0 + HOLD, len(cal) - 1)
        p0, p1 = arr[i0, col], arr[i1, col]
        r = p1 / p0 - 1
        rs = spy[i1] / spy[i0] - 1
        out[f"{name}_ret_6m"] = r
        out[f"{name}_excess_6m"] = r - rs
        out[f"{name}_complete"] = (i0 + HOLD) <= len(cal) - 1
    return pd.DataFrame(out, index=trades.index)


def member_stats(buys, sells, rets, spy, factors, rf) -> tuple[dict, dict]:
    """Performance of one member's trade-date and filing-date portfolios."""
    syms = sorted(set(buys.symbol))
    r_sub = rets[syms]
    stats, series = {}, {}
    for key, rules in [("trade", Rules.trade_date()), ("filing", Rules.filing_date())]:
        p, _ = run(buys, r_sub, rules, sells)
        live = p.ret[p.n_names > 0].dropna()
        live = live.loc[: factors.index.max()]
        s = {"invested_days": int(len(live))}
        if len(live) >= 20:
            b = spy.reindex(live.index)
            s.update({
                "ann_return": _r(metrics.ann_return(live)),
                "spy_ann_return": _r(metrics.ann_return(b)),
                "sharpe": _r(metrics.sharpe(live, rf), 3),
                "max_drawdown": _r(metrics.max_drawdown(live)),
            })
            s["excess_ann"] = _r(s["ann_return"] - s["spy_ann_return"])
        if len(live) >= MIN_DAYS:
            fit = analysis.factor_regression(live, factors, "FF5+Mom")
            s.update({"alpha_ann": _r(fit["alpha_ann"]), "alpha_t": _r(fit["alpha_t"], 2),
                      "alpha_p": _r(fit["alpha_p"], 4), "beta": _r(fit["b_Mkt-RF"], 2)})
        stats[key] = s
        if key == "trade" and len(live):
            # Weekly growth of $1 while invested, against SPY over the same days.
            g = pd.DataFrame({"member": (1 + live).cumprod(),
                              "spy": (1 + spy.reindex(live.index).fillna(0)).cumprod()})
            g = g.resample("W-FRI").last().dropna()
            series = {"dates": [d.strftime("%Y-%m-%d") for d in g.index],
                      "member": [round(v, 4) for v in g.member], "spy": [round(v, 4) for v in g.spy]}
    return stats, series


def verdict(s: dict, n_buys: int) -> str:
    if n_buys < MIN_BUYS or s.get("invested_days", 0) < MIN_DAYS or s.get("excess_ann") is None:
        return "insufficient"
    if s.get("significant"):
        return "beat_significant" if s["alpha_ann"] > 0 else "lagged_significant"
    return "beat" if s["excess_ann"] > 0 else "lagged"


def main() -> None:
    MEMBERS_DIR.mkdir(parents=True, exist_ok=True)
    trades = pd.read_parquet(PROCESSED / "trades.parquet")
    factors = load_factors()
    rf = factors.RF
    px = pd.read_parquet(prices.PRICES_PATH).sort_index()
    rets = px.pct_change(fill_method=None)
    rets = rets.where(rets < 2.0)
    spy = rets.pop("SPY")
    spy_px = px["SPY"]
    trades = trades[trades.symbol.isin(rets.columns)].copy()
    # The House writes class shares as "BRK.B", the Senate sometimes as "BRK-B".
    trades["ticker"] = trades.ticker.str.replace("-", ".", regex=False)
    # Display the priced company's clean name; the parsed House text can carry
    # stray transaction-type letters and the ticker in parentheses.
    long_name = prices.load_meta().set_index("symbol").long_name
    trades["asset_name"] = trades.symbol.map(long_name).fillna(trades.asset_name)
    trades = trades.join(trade_outcomes(trades, px, spy_px))
    states = _member_states()
    trades["member_id"] = trades.member.map(slug)

    # ---- per member -------------------------------------------------------
    rows, detail = [], {}
    for mid, g in trades.groupby("member_id"):
        buys, sells = g[g.side == "buy"], g[g.side == "sell"]
        bio = g.bioguide.dropna()
        party = g.party.mode()
        st = (g.state_dst.dropna().str[:2].mode())
        state = st.iloc[0] if len(st) else (states.get(bio.iloc[0]) if len(bio) else None)
        info = {
            "id": mid, "name": g.member.iloc[0], "chamber": g.chamber.mode().iloc[0],
            "party": party.iloc[0] if len(party) else None, "state": state,
            "n_trades": int(len(g)), "n_buys": int(len(buys)), "n_sells": int(len(sells)),
            "first_trade": g.tx_date.min().strftime("%Y-%m-%d"), "last_trade": g.tx_date.max().strftime("%Y-%m-%d"),
            "last_filing": g.filing_date.max().strftime("%Y-%m-%d"),
            "median_delay_days": int(g.delay_days.median()),
            "pct_late": _r((g.delay_days > 45).mean(), 3),
            "volume_mid": float(g.amount_mid.sum()),
        }
        done = buys[buys.trade_complete]
        info["hit_rate"] = _r((done.trade_excess_6m > 0).mean(), 3) if len(done) else None
        info["avg_buy_excess_6m"] = _r(done.trade_excess_6m.mean()) if len(done) else None
        if len(buys):
            st_, series = member_stats(buys, sells, rets, spy, factors, rf)
        else:
            st_, series = {"trade": {}, "filing": {}}, {}
        info["trade"], info["filing"] = st_["trade"], st_["filing"]
        top = buys.ticker.value_counts().head(5)
        info["top_buys"] = [{"ticker": t, "n": int(n)} for t, n in top.items()]
        rows.append(info)
        detail[mid] = (g, series)

    # Holm correction across every member that gets a verdict, per portfolio.
    for key in ("trade", "filing"):
        eligible = {m["id"]: m[key]["alpha_p"] for m in rows
                    if m["n_buys"] >= MIN_BUYS and m[key].get("alpha_p") is not None}
        adj = analysis.holm(pd.Series(eligible, dtype=float))
        for m in rows:
            s = m[key]
            s["alpha_p_holm"] = _r(adj.get(m["id"]), 4) if m["id"] in adj.index else None
            s["significant"] = bool(s["alpha_p_holm"] is not None and s["alpha_p_holm"] < 0.05)
            s["significant_unadjusted"] = bool(s.get("alpha_p") is not None and s["alpha_p"] < 0.05)
            m[f"verdict_{key}"] = verdict(s, m["n_buys"])

    # ---- write member files ------------------------------------------------
    cols = ["tx_date", "filing_date", "delay_days", "ticker", "asset_name", "side", "owner",
            "amount_raw", "amount_mid", "source_url", "trade_ret_6m", "trade_excess_6m",
            "trade_complete", "filing_excess_6m", "filing_complete"]
    for m in rows:
        g, series = detail[m["id"]]
        t = g.sort_values("tx_date", ascending=False)[cols].copy()
        t["tx_date"] = t.tx_date.dt.strftime("%Y-%m-%d")
        t["filing_date"] = t.filing_date.dt.strftime("%Y-%m-%d")
        t["asset_name"] = t.asset_name.str.slice(0, 80)
        for c in ["trade_ret_6m", "trade_excess_6m", "filing_excess_6m"]:
            t[c] = t[c].round(4)
        payload = {**m, "series": series, "trades": json.loads(t.to_json(orient="records"))}
        _dump(MEMBERS_DIR / f"{m['id']}.json", payload)

    # ---- site-wide ---------------------------------------------------------
    eligible = [m for m in rows if m["verdict_trade"] != "insufficient"]
    headline = json.loads((REPORTS / "results" / "headline.json").read_text())
    d = pd.read_csv(REPORTS / "results" / "daily_returns.csv", index_col=0, parse_dates=True)
    g = (1 + d[["trade_date", "filing_date", "spy"]].fillna(0)).cumprod().resample("W-FRI").last()
    recent = trades.sort_values(["filing_date", "tx_date"], ascending=False).head(150)
    last_year = trades[(trades.side == "buy") & (trades.filing_date > trades.filing_date.max() - pd.Timedelta(days=365))]
    most_bought = (last_year.groupby("ticker")
                   .agg(n=("ticker", "size"), members=("member_id", "nunique"), name=("asset_name", "first"))
                   .sort_values(["members", "n"], ascending=False).head(25).reset_index())
    most_bought["name"] = most_bought.name.str.slice(0, 60)
    summary = {
        "generated": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "data_through": trades.filing_date.max().strftime("%Y-%m-%d"),
        "factor_data_through": factors.index.max().strftime("%Y-%m-%d"),
        "study": {
            "sample": {k: v for k, v in headline["sample"].items() if k != "top_members"},
            "window": headline["window"],
            "summary": headline["summary"],
            "regressions": [r for r in headline["regressions"] if r["model"] == "FF5+Mom"],
            "event_study": headline["event_study"],
            "multiple_testing": headline["multiple_testing"],
        },
        "members_with_verdict": len(eligible),
        "verdict_counts": {k: {v: sum(m[f"verdict_{k}"] == v for m in rows) for v in
                               ["beat_significant", "beat", "lagged", "lagged_significant", "insufficient"]}
                           for k in ("trade", "filing")},
        "significant_unadjusted": {k: sum(m[k]["significant_unadjusted"] for m in eligible) for k in ("trade", "filing")},
        "expected_by_chance": round(0.05 * len(eligible), 1),
        "growth": {"dates": [x.strftime("%Y-%m-%d") for x in g.index],
                   "trade": g.trade_date.round(4).tolist(), "filing": g.filing_date.round(4).tolist(),
                   "spy": g.spy.round(4).tolist()},
        "most_bought": json.loads(most_bought.to_json(orient="records")),
        "recent": json.loads(recent.assign(
            tx_date=recent.tx_date.dt.strftime("%Y-%m-%d"), filing_date=recent.filing_date.dt.strftime("%Y-%m-%d"),
            asset_name=recent.asset_name.str.slice(0, 60))[
            ["member_id", "member", "chamber", "party", "tx_date", "filing_date", "delay_days", "ticker",
             "asset_name", "side", "amount_raw", "source_url"]].to_json(orient="records")),
    }
    _dump(OUT / "summary.json", summary)
    _dump(OUT / "members.json", rows)
    print(f"{len(rows)} members, {len(eligible)} with a verdict ->", OUT)
    print(json.dumps(summary["verdict_counts"], indent=1), summary["significant_unadjusted"], summary["expected_by_chance"])


if __name__ == "__main__":
    main()
