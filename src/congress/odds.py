"""Historical odds for copying a disclosed trade, and the bad-case numbers the
website's sizing calculator uses.

Nothing here predicts that a trade will win. It summarizes what happened to
past copied trades: buy the day after the disclosure, hold six months.

Member track records are noisy, so each member's hit rate is shrunk toward the
all-member rate (normal-normal empirical Bayes). Two details keep it honest:

* One filing is one decision. Trades disclosed together win or lose together,
  so each filing counts once, scored by its share of winners.
* The noise level is measured, not assumed: it is the pooled within-member
  variance of those filing scores. How much members truly differ is whatever
  dispersion is left over. If they barely differ, every member is pulled close
  to the overall rate, however lucky their own record looks.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PERCENTILES = (1, 5, 10, 25, 50, 75, 90, 95)
K_MIN, K_MAX = 5.0, 5000.0
Z80 = 1.2816


def outcome_stats(ret: pd.Series, excess: pd.Series, month: pd.Series) -> dict:
    """Hit rate vs SPY with a month-clustered 95% CI, plus the return distribution.

    Trades disclosed in the same month share market moves, so the interval
    treats each month as one observation rather than each trade.
    """
    df = pd.DataFrame({"ret": ret, "excess": excess, "month": month}).dropna()
    if df.empty:
        return {"n": 0}
    hit = (df.excess > 0).astype(float)
    by_month = hit.groupby(df.month).mean()
    se = by_month.std(ddof=1) / np.sqrt(len(by_month)) if len(by_month) > 1 else np.nan
    p = float(hit.mean())
    return {
        "n": int(len(df)), "hit_rate": p,
        "hit_ci": [max(0.0, p - 1.96 * se), min(1.0, p + 1.96 * se)] if np.isfinite(se) else None,
        "mean_excess": float(df.excess.mean()), "median_return": float(df.ret.median()),
        "pct_lost_money": float((df.ret < 0).mean()),
        "return_percentiles": {f"p{q}": float(np.percentile(df.ret, q)) for q in PERCENTILES},
    }


def filing_scores(member: pd.Series, filing: pd.Series, won: pd.Series) -> tuple[pd.DataFrame, float]:
    """Per member: number of filings and mean filing score; plus the pooled
    within-member variance of one filing's score (the noise per decision)."""
    f = pd.DataFrame({"m": member.values, "f": filing.values, "w": won.astype(float).values})
    score = f.groupby(["m", "f"]).w.mean().rename("s").reset_index()
    per = score.groupby("m").s.agg(n="size", rate="mean")
    dev = score.s - score.groupby("m").s.transform("mean")
    dof = len(score) - score.m.nunique()
    unit_var = float((dev ** 2).sum() / dof) if dof > 0 else 0.25
    return per, unit_var


def shrinkage_strength(rates: np.ndarray, n: np.ndarray, unit_var: float) -> float:
    """Prior strength k, in filings: noise variance / true between-member variance.

    True variance = observed variance of member rates minus the part sampling
    noise alone explains. None left over means a very large k (full pooling).
    """
    tau2 = np.var(rates, ddof=1) - np.mean(unit_var / n)
    if not np.isfinite(tau2) or tau2 <= 0:
        return K_MAX
    return float(np.clip(unit_var / tau2, K_MIN, K_MAX))


def member_odds(rate: float, n: int, p: float, k: float, unit_var: float) -> dict:
    """Shrunk hit rate and an 80% range for one member (n = filings)."""
    mean = (n * rate + k * p) / (n + k)
    sd = np.sqrt(unit_var / (n + k))
    return {"n": int(n), "raw_rate": float(rate), "odds": float(mean),
            "odds_range": [float(max(0.0, mean - Z80 * sd)), float(min(1.0, mean + Z80 * sd))]}


def persistence_check(member: pd.Series, filing: pd.Series, won: pd.Series,
                      cut: str = "2021-01-01", min_filings: int = 10) -> dict:
    """Do odds estimated before `cut` predict members' hit rates after it?

    Fits the shrinkage on the early period only, then compares each member's
    early odds with their realized later rate (members with enough filings in
    both periods). This is the out-of-sample test of whether the odds mean anything.
    """
    from scipy import stats

    early = filing < pd.Timestamp(cut)
    pe, uv = filing_scores(member[early], filing[early], won[early])
    fit = pe[pe.n >= min_filings]
    k = shrinkage_strength(fit.rate.to_numpy(), fit.n.to_numpy(float), uv)
    p = float(won[early].mean())
    pl, _ = filing_scores(member[~early], filing[~early], won[~early])
    both = pe.join(pl, lsuffix="_e", rsuffix="_l", how="inner")
    both = both[(both.n_e >= min_filings) & (both.n_l >= min_filings)]
    pred = (both.n_e * both.rate_e + k * p) / (both.n_e + k)
    r, pv = stats.pearsonr(pred, both.rate_l)
    order = pred.sort_values()
    third = len(order) // 3
    return {
        "cut": cut, "members": int(len(both)), "corr": float(r), "p_value": float(pv),
        "top_third_predicted": float(pred[order.index[-third:]].mean()),
        "top_third_realized": float(both.rate_l[order.index[-third:]].mean()),
        "bottom_third_predicted": float(pred[order.index[:third]].mean()),
        "bottom_third_realized": float(both.rate_l[order.index[:third]].mean()),
    }
