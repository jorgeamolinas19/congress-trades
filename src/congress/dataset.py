"""Join cleaned trades to price data and apply the price-side filters.

Adds to the cleaning waterfall:
  * tickers yfinance cannot price at all (mostly delisted -> survivorship bias)
  * instruments yfinance classifies as ETFs / funds rather than common equity
  * tickers with no price on the trade date (delisted before, or a recycled symbol)
  * name mismatches between the filing and the priced security (recycled symbols)
"""
from __future__ import annotations

import re

import pandas as pd

from . import prices
from .config import PROCESSED

STOP = {"inc", "corp", "corporation", "co", "company", "the", "ltd", "plc", "holdings", "holding",
        "group", "class", "common", "stock", "shares", "ordinary", "sa", "nv", "ag", "se", "lp",
        "llc", "a", "b", "c", "of", "and", "de", "new", "com", "cl", "adr", "ads", "sponsored", "international"}


def _tokens(s) -> set[str]:
    words = re.findall(r"[a-z0-9]+", str(s).lower())
    return {w for w in words if w not in STOP and len(w) > 1}


def name_overlap(filed: str, priced: str) -> bool:
    """Does the filed asset name share any distinctive word with the priced name?"""
    a, b = _tokens(filed), _tokens(priced)
    if not a or not b:
        return True  # nothing to compare; don't penalise
    if a & b:
        return True
    # Prefix match catches abbreviations like "Intl Bus Mach" / "International Business Machines".
    return any(x[:4] == y[:4] for x in a for y in b if len(x) >= 4 and len(y) >= 4)


def build() -> pd.DataFrame:
    df = pd.read_parquet(PROCESSED / "trades_stage1.parquet")
    steps = pd.read_csv(PROCESSED / "cleaning_waterfall.csv")
    steps = steps[~steps.step.str.startswith("[price]")]
    add = []

    df["symbol"] = df.ticker.map(prices.yf_symbol)
    prices.download(sorted(set(df.symbol)) + ["SPY"])
    meta = prices.load_meta().set_index("symbol")

    def keep(mask, label):
        nonlocal df
        df = df[mask]
        add.append((f"[price] {label}", len(df)))

    keep(df.symbol.map(meta.status).eq("ok"), "drop tickers with no yfinance data (delisted / unknown)")
    keep(df.symbol.map(meta.instrument_type).eq("EQUITY"), "drop ETFs, funds and other non-equity per yfinance")
    first = pd.to_datetime(df.symbol.map(meta["first"]))
    keep(first <= df.tx_date, "drop tickers with no price history on the trade date")
    # Hand-verified renames ("Square" -> "Block, Inc.") are exempt from the name check.
    ok = [t in prices.RENAMES or name_overlap(a, b)
          for t, a, b in zip(df.ticker, df.asset_name, df.symbol.map(meta.long_name))]
    keep(pd.Series(ok, index=df.index), "drop filed-name vs priced-name mismatches (recycled tickers)")

    df = df.reset_index(drop=True)
    df.to_parquet(PROCESSED / "trades.parquet")
    pd.concat([steps, pd.DataFrame(add, columns=steps.columns)]).to_csv(
        PROCESSED / "cleaning_waterfall.csv", index=False)
    return df
