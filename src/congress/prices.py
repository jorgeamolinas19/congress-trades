"""Daily total-return prices from yfinance, with instrument-type metadata.

Prices are dividend- and split-adjusted closes (auto_adjust=True). yfinance does
not carry most delisted securities, so tickers that return no data are recorded
in the metadata file; the cleaning step reports how many trades that loses
(survivorship bias).
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import yfinance as yf

from .config import INTERIM

PRICES_PATH = INTERIM / "prices.parquet"
META_PATH = INTERIM / "price_meta.csv"

# Ticker changes where the same legal entity kept trading, so an old symbol on a
# filing maps to a continuous price history. Each successor was checked to have
# yfinance history back to 2013. Mergers where the filed company's own shares
# stopped trading (e.g. RTN, TWTR, CELG) are deliberately NOT mapped: those are
# genuine delistings and are counted as survivorship losses.
RENAMES = {
    "FB": "META", "ANTM": "ELV", "ABC": "COR", "PKI": "RVTY", "WLTW": "WTW",
    "CTL": "LUMN", "HFC": "DINO", "RE": "EG", "ADS": "BFH", "FLT": "CPAY",
    "GPS": "GAP", "BLL": "BALL", "SQ": "XYZ", "UTX": "RTX", "DISCA": "WBD",
    "DISCK": "WBD", "BK": "BNY", "MMC": "MRSH", "CBS": "PSKY", "VIAC": "PSKY",
    "PARA": "PSKY", "KORS": "CPRI", "HCN": "WELL", "BBT": "TFC", "SNE": "SONY",
    "HHC": "HHH", "RDS.A": "SHEL", "RDS.B": "SHEL",
}


def yf_symbol(ticker: str) -> str:
    t = RENAMES.get(ticker, ticker)
    return t.replace(".", "-").replace("/", "-")


def _one(sym: str, start: str, end: str, attempts: int = 5):
    for attempt in range(attempts):
        out = _one_try(sym, start, end)
        if out[2]["status"] != "error:YFRateLimitError":
            return out
        time.sleep(30 * (attempt + 1))
    return out


def _one_try(sym: str, start: str, end: str):
    try:
        tk = yf.Ticker(sym)
        h = tk.history(start=start, end=end, auto_adjust=True, actions=False)
        meta = tk.history_metadata or {}
        if h.empty:
            return sym, None, {"symbol": sym, "status": "no_data"}
        s = h["Close"]
        s.index = s.index.tz_localize(None).normalize()
        return sym, s, {
            "symbol": sym, "status": "ok", "instrument_type": meta.get("instrumentType"),
            "exchange": meta.get("exchangeName"), "first": s.index.min().date(), "last": s.index.max().date(),
            "long_name": meta.get("longName"),
        }
    except Exception as e:  # yfinance raises on many delisted symbols
        return sym, None, {"symbol": sym, "status": f"error:{type(e).__name__}"}


def _tomorrow() -> str:
    return (pd.Timestamp.today().normalize() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")


def merge_history(old: pd.Series, new: pd.Series) -> pd.Series:
    """Combine an existing price history with a fresh download of the same stock.

    A full re-download replaces the old history only when it covers all of it
    (it then also picks up dividend re-basing). Yahoo sometimes returns a
    truncated or partial series; replacing a long history with it silently
    deletes years of data. In that case the old history is kept and only the
    newer days are spliced on, scaled to the old price basis at their last
    common day. With nothing to anchor on, the old history is left untouched.
    """
    old, new = old.dropna(), new.dropna()
    if new.empty:
        return old
    if old.empty:
        return new
    in_range = new.loc[old.index.min():old.index.max()]
    if new.index.min() <= old.index.min() + pd.Timedelta(days=7) and len(in_range) >= 0.98 * len(old):
        return new
    common = old.index.intersection(new.index)
    if len(common) == 0:
        return old
    anchor = common.max()
    tail = new.loc[new.index > old.index.max()] * (old[anchor] / new[anchor])
    return pd.concat([old, tail])


def refresh(symbols: list[str], start: str = "2013-01-01", chunk: int = 100) -> int:
    """Re-download full adjusted history for `symbols` in batches and replace
    them in the cache. Used daily for recently traded symbols (a full
    re-download, not an append, because dividend adjustments rescale history)."""
    px = pd.read_parquet(PRICES_PATH)
    symbols = sorted(set(symbols) & set(px.columns))
    updated = 0
    for i in range(0, len(symbols), chunk):
        batch = symbols[i:i + chunk]
        for attempt in range(4):
            try:
                data = yf.download(batch, start=start, end=_tomorrow(), auto_adjust=True,
                                   progress=False, threads=True, group_by="column")
                break
            except Exception:
                time.sleep(30 * (attempt + 1))
        else:
            continue
        close = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data[["Close"]].set_axis(batch, axis=1)
        close.index = close.index.tz_localize(None).normalize()
        good = [c for c in close.columns if close[c].notna().sum() > 0]
        merged = {c: merge_history(px[c], close[c]) for c in good}
        px = px.reindex(px.index.union(close.index))
        for c, series in merged.items():
            px[c] = series.reindex(px.index)
        updated += len(good)
    px.sort_index().to_parquet(PRICES_PATH)
    return updated


def download(symbols: list[str], start: str = "2013-01-01", end: str | None = None,
             retry_failed: bool = False, threads: int = 8) -> pd.DataFrame:
    """Download (or extend the cache with) adjusted closes for `symbols`.

    yfinance throttles bursts and then reports live tickers as "no data", so
    `retry_failed=True` re-queries every non-ok symbol (use a low thread count).
    """
    cached = pd.read_parquet(PRICES_PATH) if PRICES_PATH.exists() else pd.DataFrame()
    meta = pd.read_csv(META_PATH) if META_PATH.exists() else pd.DataFrame(columns=["symbol", "status"])
    if retry_failed:
        meta = meta[meta.status == "ok"]
    end = end or _tomorrow()
    todo = sorted(set(symbols) - set(meta.symbol))
    if todo:
        with ThreadPoolExecutor(threads) as ex:
            res = list(ex.map(lambda s: _one(s, start, end), todo))
        new = {s: p for s, p, _ in res if p is not None}
        if new:
            cached = pd.concat([cached, pd.DataFrame(new)], axis=1)
        meta = pd.concat([meta, pd.DataFrame([m for _, _, m in res])], ignore_index=True)
        cached.sort_index().to_parquet(PRICES_PATH)
        meta.to_csv(META_PATH, index=False)
    return cached.sort_index()


def load_returns() -> pd.DataFrame:
    """Daily simple returns, one column per yfinance symbol."""
    px = pd.read_parquet(PRICES_PATH).sort_index()
    return px.pct_change(fill_method=None)


def load_meta() -> pd.DataFrame:
    return pd.read_csv(META_PATH)
