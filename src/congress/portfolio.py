"""Calendar-time copycat portfolios.

Each disclosed purchase opens a position in that stock. A position earns the
stock's daily return from the day after entry until it exits. The portfolio's
daily return is the weighted average return of all open positions (weights held
constant, i.e. rebalanced daily).

Timing conventions (the core of the look-ahead question):
  * trade-date portfolio  - enter at the close of the transaction date. Not
    investable: nobody outside the member's household knows about the trade yet.
  * filing-date portfolio - enter at the close of the first trading day AFTER
    the filing date. Filings can be posted after the close, so entering on the
    filing date itself could use information before it was public.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Rules:
    """Portfolio construction rules. Defaults are the headline specification."""

    date_col: str = "filing_date"   # 'tx_date' (theoretical) or 'filing_date' (investable)
    entry_lag: int = 1              # trading days after the event date before entering
    hold_days: int = 126            # ~6 months of trading days
    weight: str = "equal"           # 'equal' or an amount column, e.g. 'amount_mid'
    exit_on_sale: bool = False      # also exit when the member's own sale becomes known

    @classmethod
    def trade_date(cls, **kw) -> "Rules":
        return cls(date_col="tx_date", entry_lag=0, **kw)

    @classmethod
    def filing_date(cls, **kw) -> "Rules":
        return cls(date_col="filing_date", entry_lag=1, **kw)


def _sale_known_dates(sells: pd.DataFrame, rules: Rules) -> pd.DataFrame:
    """When each member's sale of each symbol becomes known under these rules."""
    return sells[["member", "symbol", rules.date_col]].rename(columns={rules.date_col: "sale_date"})


def build_positions(buys: pd.DataFrame, calendar: pd.DatetimeIndex, rules: Rules,
                    sells: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per position: symbol, entry index, exit index (inclusive), weight.

    The position earns returns on calendar rows entry_i+1 .. exit_i.
    """
    ev = buys.copy()
    day0 = calendar.searchsorted(ev[rules.date_col].values, side="left")
    ev["entry_i"] = day0 + rules.entry_lag
    ev["exit_i"] = ev.entry_i + rules.hold_days

    if rules.exit_on_sale and sells is not None and len(sells):
        s = _sale_known_dates(sells, rules)
        s["sale_i"] = calendar.searchsorted(s.sale_date.values, side="left") + rules.entry_lag
        m = ev.reset_index().merge(s, on=["member", "symbol"], how="left")
        # Only a sale that becomes known after we entered can close the position.
        m = m[m.sale_i.isna() | (m.sale_i > m.entry_i)]
        first_sale = m.groupby("index").sale_i.min()
        ev["exit_i"] = np.minimum(ev.exit_i, first_sale.reindex(ev.index).fillna(np.inf)).astype(int)

    ev["w"] = 1.0 if rules.weight == "equal" else ev[rules.weight].astype(float)
    ev = ev[(ev.entry_i < len(calendar) - 1) & (ev.w > 0)]
    ev["exit_i"] = ev.exit_i.clip(upper=len(calendar) - 1)
    return ev


def weight_matrix(positions: pd.DataFrame, calendar: pd.DatetimeIndex, symbols: pd.Index) -> pd.DataFrame:
    """Raw (unnormalised) weight held in each symbol on each day."""
    col = symbols.get_indexer(positions.symbol)
    if (col < 0).any():
        raise ValueError("positions reference symbols with no return series")
    diff = np.zeros((len(calendar) + 1, len(symbols)))
    np.add.at(diff, (positions.entry_i.values + 1, col), positions.w.values)
    np.add.at(diff, (positions.exit_i.values + 1, col), -positions.w.values)
    w = np.cumsum(diff[:-1], axis=0)
    w[np.abs(w) < 1e-9] = 0.0
    return pd.DataFrame(w, index=calendar, columns=symbols)


def portfolio_returns(weights: pd.DataFrame, returns: pd.DataFrame) -> pd.DataFrame:
    """Daily return, number of names held and total weight.

    A stock with no return on a day (halted, or its history ends mid-hold) is
    dropped for that day and the remaining weights are renormalised.
    """
    r = returns.reindex(index=weights.index, columns=weights.columns)
    live = weights.where(r.notna(), 0.0)
    tot = live.sum(axis=1)
    ret = (live * r.fillna(0.0)).sum(axis=1) / tot.replace(0, np.nan)
    return pd.DataFrame({"ret": ret, "n_names": (live > 0).sum(axis=1), "gross": tot})


def run(buys: pd.DataFrame, returns: pd.DataFrame, rules: Rules,
        sells: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Positions and daily portfolio series for one rule set."""
    cal = returns.index
    pos = build_positions(buys, cal, rules, sells)
    W = weight_matrix(pos, cal, returns.columns)
    return portfolio_returns(W, returns), W
