"""Factor regressions, event study, concentration and multiple-testing tools."""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

TRADING_DAYS = 252
MODELS = {
    "CAPM": ["Mkt-RF"],
    "FF3": ["Mkt-RF", "SMB", "HML"],
    "FF5": ["Mkt-RF", "SMB", "HML", "RMW", "CMA"],
    "FF5+Mom": ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"],
}


# --------------------------------------------------------------------------- #
# Factor regression
# --------------------------------------------------------------------------- #
def factor_regression(r: pd.Series, factors: pd.DataFrame, model: str = "FF5+Mom",
                      excess: bool = True, hac_lags: int = 10) -> dict:
    """OLS of daily (excess) returns on factors with Newey-West standard errors.

    `excess=False` is for long-short / difference series, which are already
    zero-investment and must not have the risk-free rate subtracted.
    """
    cols = MODELS[model]
    df = pd.concat([r.rename("r"), factors], axis=1, join="inner").dropna()
    y = df.r - df.RF if excess else df.r
    X = sm.add_constant(df[cols])
    fit = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": hac_lags})
    out = {
        "model": model, "n_days": int(fit.nobs),
        "alpha_ann": float(fit.params["const"] * TRADING_DAYS),
        "alpha_t": float(fit.tvalues["const"]), "alpha_p": float(fit.pvalues["const"]),
        "r2": float(fit.rsquared),
    }
    for c in cols:
        out[f"b_{c}"] = float(fit.params[c])
        out[f"t_{c}"] = float(fit.tvalues[c])
    return out


# --------------------------------------------------------------------------- #
# Event study
# --------------------------------------------------------------------------- #
def abnormal_returns(returns: pd.DataFrame, bench: pd.Series) -> pd.DataFrame:
    """Market-adjusted abnormal returns: stock return minus SPY return."""
    return returns.sub(bench.reindex(returns.index), axis=0)


def event_paths(events: pd.DataFrame, ar: pd.DataFrame, date_col: str,
                pre: int = 20, post: int = 126) -> pd.DataFrame:
    """Abnormal-return paths, one row per event, columns = event day -pre..post.

    Day 0 is the first trading day on/after the event date; its return is the
    close(-1)->close(0) move, so CAR over days 1..k is what a buyer at the
    day-0 close earns.
    """
    cal = ar.index
    arr = ar.to_numpy()
    col = ar.columns.get_indexer(events.symbol)
    d0 = cal.searchsorted(events[date_col].values, side="left")
    rel = np.arange(-pre, post + 1)
    idx = d0[:, None] + rel[None, :]
    ok = (idx >= 0) & (idx < len(cal))
    out = np.full(idx.shape, np.nan)
    rows, cols_ = np.nonzero(ok)
    out[rows, cols_] = arr[idx[rows, cols_], col[rows]]
    return pd.DataFrame(out, index=events.index, columns=rel)


def car(paths: pd.DataFrame, start: int, end: int) -> pd.Series:
    """Cumulative abnormal return over event days start..end (inclusive).

    Events with any missing day in the window are dropped rather than
    silently treated as zero.
    """
    win = paths.loc[:, start:end]
    return win.sum(axis=1, min_count=1).where(win.notna().all(axis=1))


def clustered_mean(x: pd.Series, clusters: pd.Series) -> dict:
    """Mean with a t-stat that treats each calendar month as one observation.

    Events in the same month share market shocks, so the naive cross-sectional
    t-stat overstates precision. Averaging within month, then across months,
    is a conservative fix (Fama-MacBeth style).
    """
    df = pd.DataFrame({"x": x, "c": clusters}).dropna()
    m = df.groupby("c").x.mean()
    se = m.std(ddof=1) / np.sqrt(len(m))
    return {"mean": float(df.x.mean()), "month_mean": float(m.mean()),
            "t_clustered": float(m.mean() / se), "n_events": int(len(df)), "n_months": int(len(m))}


def delay_car(events: pd.DataFrame, ar: pd.DataFrame) -> pd.Series:
    """Per-event abnormal return between the trade-date close and the copier's
    entry (close of the trading day after filing): what the delay costs."""
    cal = ar.index
    arr = ar.to_numpy()
    col = ar.columns.get_indexer(events.symbol)
    t0 = cal.searchsorted(events.tx_date.values, side="left")
    t1 = cal.searchsorted(events.filing_date.values, side="left") + 1
    cs = np.vstack([np.zeros(arr.shape[1]), np.nancumsum(np.nan_to_num(arr), axis=0)])
    valid = (t1 < len(cal)) & (t1 > t0)
    out = np.full(len(events), np.nan)
    out[valid] = cs[t1[valid] + 1, col[valid]] - cs[t0[valid] + 1, col[valid]]
    return pd.Series(out, index=events.index)


# --------------------------------------------------------------------------- #
# Concentration
# --------------------------------------------------------------------------- #
def concentration(W: pd.DataFrame, returns: pd.DataFrame, top: int = 10) -> dict:
    """Average top-N weight, and each name's share of the portfolio's return."""
    live = W.where(returns.reindex_like(W).notna(), 0.0)
    w = live.div(live.sum(axis=1).replace(0, np.nan), axis=0).dropna(how="all")
    top_w = w.apply(lambda row: row.nlargest(top).sum(), axis=1)
    contrib = (w * returns.reindex_like(w).fillna(0.0)).sum()
    return {
        "avg_top_weight": float(top_w.mean()),
        "avg_names": float((w > 0).sum(axis=1).mean()),
        "contribution": contrib.sort_values(ascending=False),
        "avg_weight": w.mean().sort_values(ascending=False),
    }


# --------------------------------------------------------------------------- #
# Multiple testing
# --------------------------------------------------------------------------- #
def holm(pvals: pd.Series) -> pd.Series:
    """Holm-Bonferroni adjusted p-values (controls family-wise error rate)."""
    p = pvals.dropna().sort_values()
    m = len(p)
    adj = np.maximum.accumulate((m - np.arange(m)) * p.values)
    return pd.Series(np.minimum(adj, 1.0), index=p.index).reindex(pvals.index)
