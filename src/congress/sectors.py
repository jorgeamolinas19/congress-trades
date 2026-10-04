"""GICS-style sector labels from yfinance, cached (one lookup per symbol)."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import yfinance as yf

from .config import INTERIM

PATH = INTERIM / "sectors.csv"


def _one(sym: str, attempts: int = 5) -> dict:
    for attempt in range(attempts):
        try:
            info = yf.Ticker(sym).info
            return {"symbol": sym, "sector": info.get("sector"), "industry": info.get("industry")}
        except Exception as e:
            if type(e).__name__ != "YFRateLimitError":
                break
            time.sleep(30 * (attempt + 1))
    return {"symbol": sym, "sector": None, "industry": None}


def load(symbols: list[str]) -> pd.Series:
    have = pd.read_csv(PATH) if PATH.exists() else pd.DataFrame(columns=["symbol", "sector", "industry"])
    todo = sorted(set(symbols) - set(have.symbol))
    if todo:
        with ThreadPoolExecutor(3) as ex:
            have = pd.concat([have, pd.DataFrame(list(ex.map(_one, todo)))], ignore_index=True)
        have.to_csv(PATH, index=False)
    return have.set_index("symbol").sector.fillna("Unknown")
