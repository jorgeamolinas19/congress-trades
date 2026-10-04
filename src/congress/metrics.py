"""Performance statistics for daily return series."""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def ann_return(r: pd.Series) -> float:
    r = r.dropna()
    return float((1 + r).prod() ** (TRADING_DAYS / len(r)) - 1)


def ann_vol(r: pd.Series) -> float:
    return float(r.dropna().std() * np.sqrt(TRADING_DAYS))


def sharpe(r: pd.Series, rf: pd.Series) -> float:
    ex = (r - rf.reindex(r.index)).dropna()
    return float(ex.mean() / ex.std() * np.sqrt(TRADING_DAYS))


def max_drawdown(r: pd.Series) -> float:
    wealth = (1 + r.dropna()).cumprod()
    return float((wealth / wealth.cummax() - 1).min())


def tracking_error(r: pd.Series, bench: pd.Series) -> float:
    return float((r - bench.reindex(r.index)).dropna().std() * np.sqrt(TRADING_DAYS))


def information_ratio(r: pd.Series, bench: pd.Series) -> float:
    d = (r - bench.reindex(r.index)).dropna()
    return float(d.mean() / d.std() * np.sqrt(TRADING_DAYS))


def beta(r: pd.Series, bench: pd.Series) -> float:
    df = pd.concat([r, bench], axis=1).dropna()
    c = np.cov(df.iloc[:, 0], df.iloc[:, 1])
    return float(c[0, 1] / c[1, 1])


def summary(r: pd.Series, bench: pd.Series, rf: pd.Series) -> dict:
    return {
        "ann_return": ann_return(r), "ann_vol": ann_vol(r), "sharpe": sharpe(r, rf),
        "max_drawdown": max_drawdown(r), "beta_spy": beta(r, bench),
        "tracking_error": tracking_error(r, bench), "info_ratio": information_ratio(r, bench),
        "n_days": int(r.notna().sum()),
    }
