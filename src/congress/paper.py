"""A $1,000 paper-trading account, replayed from decisions and real prices.

The account is never stored; it is recomputed from the list of decisions every
time, so it cannot drift and any rule change can be replayed over the whole
history. A decision is one line: which symbol, buy or sell, and the date of the
last close the decider could see (`data_date`).

Rules (see `Rules`):
  * A buy invests a fixed dollar amount (default $100), at most one position per
    symbol, at most `max_positions` open, no leverage, no shorting.
  * A sell closes the position if one is held; otherwise it does nothing.
  * Every fill happens at the CLOSE of the first trading day strictly after
    `data_date`, so a decision never trades on prices it could already see.
    Fills include slippage against you (default 0.1%).
  * A position is closed automatically `hold_days` trading days after entry,
    at that day's close.
  * Unfilled orders are reported with the reason (no cash, slots full, ...).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Rules:
    start_cash: float = 1000.0
    position_usd: float = 100.0
    max_positions: int = 10
    hold_days: int = 20          # trading days
    slippage: float = 0.001      # applied against you on every fill


def fill_index(cal: pd.DatetimeIndex, data_date) -> int | None:
    """Index of the first trading day strictly after `data_date`, or None if it
    has not traded yet."""
    i = int(cal.searchsorted(pd.Timestamp(data_date), side="right"))
    return i if i < len(cal) else None


def _iso(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def simulate(decisions: list[dict], closes: pd.DataFrame, rules: Rules = Rules(), start=None) -> dict:
    """Replay `decisions` over `closes` (columns are symbols, index trading days).

    Each decision needs: id, symbol, ticker, action ('buy'|'sell'), data_date,
    and optionally `priority` (higher fills first among same-day buys).
    """
    closes = closes.sort_index().ffill()
    cal = closes.index
    empty = {"equity": [], "positions": [], "closed": [], "outcomes": {}, "cash": rules.start_cash, "start": None}
    if not decisions or len(cal) == 0:
        return empty
    start = pd.Timestamp(start) if start is not None else min(pd.Timestamp(d["data_date"]) for d in decisions)
    start_i = int(cal.searchsorted(start, side="right"))
    outcomes: dict[str, dict] = {}
    by_day: dict[int, list[dict]] = defaultdict(list)
    for d in decisions:
        fi = fill_index(cal, d["data_date"])
        if fi is None:
            outcomes[d["id"]] = {"status": "pending", "note": "Fills at the next close, which hasn't happened yet."}
        else:
            by_day[max(fi, start_i)].append(d)
    if start_i >= len(cal):
        return {**empty, "outcomes": outcomes, "start": _iso(start)}

    cash = rules.start_cash
    positions: dict[str, dict] = {}
    closed: list[dict] = []
    equity: list[dict] = []

    def price(sym: str, i: int) -> float:
        return float(closes[sym].iloc[i]) if sym in closes.columns else float("nan")

    def close_position(sym: str, i: int, reason: str) -> None:
        nonlocal cash
        p = positions.pop(sym)
        exit_price = price(sym, i) * (1 - rules.slippage)
        proceeds = p["shares"] * exit_price
        cash += proceeds
        closed.append({
            "ticker": p["ticker"], "symbol": sym, "decision_id": p["decision_id"],
            "entry_date": _iso(cal[p["entry_i"]]), "entry_price": p["entry_price"],
            "exit_date": _iso(cal[i]), "exit_price": exit_price, "shares": p["shares"],
            "cost": p["cost"], "pnl": proceeds - p["cost"], "pnl_pct": proceeds / p["cost"] - 1,
            "days_held": i - p["entry_i"], "reason": reason,
        })

    for i in range(start_i, len(cal)):
        # 1. Time exits come first, freeing cash and slots for today's buys.
        for sym in [s for s, p in positions.items() if p["exit_i"] == i]:
            close_position(sym, i, "time")
        todays = by_day.get(i, [])
        # 2. Sells.
        for d in [x for x in todays if x["action"] == "sell"]:
            if d["symbol"] in positions:
                close_position(d["symbol"], i, "sell signal")
                outcomes[d["id"]] = {"status": "filled", "date": _iso(cal[i]), "note": "Closed the position."}
            else:
                outcomes[d["id"]] = {"status": "skipped", "note": "Sell signal, but the account holds none of it."}
        # 3. Buys, highest priority first.
        for d in sorted((x for x in todays if x["action"] == "buy"), key=lambda x: -(x.get("priority") or 0)):
            sym = d["symbol"]
            px = price(sym, i)
            if sym in positions:
                outcomes[d["id"]] = {"status": "skipped", "note": "Already holding it."}
            elif not np.isfinite(px):
                outcomes[d["id"]] = {"status": "skipped", "note": "No price data for this symbol."}
            elif len(positions) >= rules.max_positions:
                outcomes[d["id"]] = {"status": "skipped", "note": f"All {rules.max_positions} position slots were full."}
            elif cash < rules.position_usd - 1e-9:
                outcomes[d["id"]] = {"status": "skipped", "note": "Not enough cash."}
            else:
                entry = px * (1 + rules.slippage)
                cash -= rules.position_usd
                positions[sym] = {"ticker": d["ticker"], "decision_id": d["id"], "entry_i": i, "entry_price": entry,
                                  "shares": rules.position_usd / entry, "cost": rules.position_usd,
                                  "exit_i": i + rules.hold_days}
                outcomes[d["id"]] = {"status": "filled", "date": _iso(cal[i]), "price": entry,
                                     "note": f"Bought ${rules.position_usd:,.0f} at the close."}
        value = cash + sum(p["shares"] * price(s, i) for s, p in positions.items())
        equity.append({"date": _iso(cal[i]), "value": float(value)})

    last = len(cal) - 1
    open_positions = []
    for sym, p in positions.items():
        px = price(sym, last)
        exit_day = cal[p["exit_i"]] if p["exit_i"] < len(cal) else pd.bdate_range(cal[last], periods=p["exit_i"] - last + 1)[-1]
        open_positions.append({
            "ticker": p["ticker"], "symbol": sym, "decision_id": p["decision_id"], "entry_date": _iso(cal[p["entry_i"]]),
            "entry_price": p["entry_price"], "shares": p["shares"], "cost": p["cost"], "price": px,
            "value": p["shares"] * px, "pnl": p["shares"] * px - p["cost"], "pnl_pct": p["shares"] * px / p["cost"] - 1,
            "days_held": last - p["entry_i"], "exit_due": _iso(exit_day),
        })
    return {"equity": equity, "positions": open_positions, "closed": closed, "outcomes": outcomes,
            "cash": cash, "start": _iso(cal[start_i])}


def benchmark_curve(closes: pd.DataFrame, symbol: str, start, start_cash: float = 1000.0) -> list[dict]:
    """Buy-and-hold of `symbol`, bought at the close of the account's first day."""
    closes = closes.sort_index().ffill()
    i0 = int(closes.index.searchsorted(pd.Timestamp(start), side="right"))
    if symbol not in closes.columns or i0 >= len(closes):
        return []
    s = closes[symbol].iloc[i0:]
    return [{"date": _iso(d), "value": float(start_cash * v / s.iloc[0])} for d, v in s.items()]


def summarize(result: dict, start_cash: float) -> dict:
    """Headline numbers for one account."""
    eq = [e["value"] for e in result["equity"]]
    closed = result["closed"]
    value = eq[-1] if eq else start_cash
    peak = np.maximum.accumulate(eq) if eq else []
    dd = float(np.min(np.array(eq) / peak - 1)) if eq else 0.0
    wins = [c for c in closed if c["pnl"] > 0]
    return {
        "value": value, "return": value / start_cash - 1, "max_drawdown": dd,
        "cash": result["cash"], "n_open": len(result["positions"]), "n_closed": len(closed),
        "win_rate": (len(wins) / len(closed)) if closed else None,
        "avg_trade_pct": float(np.mean([c["pnl_pct"] for c in closed])) if closed else None,
    }
