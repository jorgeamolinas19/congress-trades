"""Data validation.

1. Automated: compare our Senate parse against the independent Senate Stock
   Watcher dataset (2014-2020), matching on senator, ticker, date, side, amount.
2. Manual: draw a stratified sample of 50 cleaned trades with links to the
   original filings, for a human to check line by line.
"""
from __future__ import annotations

import json

import pandas as pd

from .clean import SIDE, _norm_name
from .config import PROCESSED, RAW

MIRROR = RAW / "senate_watcher_all.json"


def _mirror_last(name: str) -> str:
    """'David A Perdue, Jr' -> 'perdue' (drop suffixes before taking the surname)."""
    words = [w for w in str(name).replace(",", " ").split()
             if w.lower().strip(".") not in {"jr", "sr", "ii", "iii", "iv"}]
    return _norm_name(words[-1]) if words else ""


def senate_crosscheck(trades: pd.DataFrame) -> dict:
    """Two-way match rate between our Senate stock trades and the mirror.

    Pass the pre-price-filter trades (trades_stage1) so both sides have had the
    same filters applied: stock rows with a ticker, buys and sells only.
    """
    m = pd.DataFrame(json.loads(MIRROR.read_text(encoding="utf-8")))
    m = m[m.asset_type.isin(["Stock"]) & m.ticker.ne("--")]
    m = pd.DataFrame({
        "last": m.senator.map(_mirror_last),
        "ticker": m.ticker.str.upper().str.strip(),
        "tx_date": pd.to_datetime(m.transaction_date, errors="coerce"),
        "side": m.type.map(SIDE), "amount_raw": m.amount.str.strip(),
    })
    m = m[m.tx_date.between("2014-01-01", "2020-11-30") & m.side.isin(["buy", "sell"])]

    ours = trades[(trades.chamber == "Senate") & trades.tx_date.between("2014-01-01", "2020-11-30")]
    ours = pd.DataFrame({
        "last": ours.last_name.map(_norm_name), "ticker": ours.ticker, "tx_date": ours.tx_date,
        "side": ours.side, "amount_raw": ours.amount_raw.str.strip(),
    })
    key = ["last", "ticker", "tx_date", "side", "amount_raw"]
    ours_k, m_k = ours.drop_duplicates(key), m.drop_duplicates(key)
    both = ours_k.merge(m_k, on=key, how="inner")
    only_ours = ours_k.merge(m_k, on=key, how="left", indicator=True).query("_merge == 'left_only'")
    only_mirror = m_k.merge(ours_k, on=key, how="left", indicator=True).query("_merge == 'left_only'")
    only_ours.drop(columns="_merge").to_csv(PROCESSED / "crosscheck_only_ours.csv", index=False)
    only_mirror.drop(columns="_merge").to_csv(PROCESSED / "crosscheck_only_mirror.csv", index=False)
    return {
        "ours": len(ours_k), "mirror": len(m_k), "matched": len(both),
        "pct_ours_in_mirror": len(both) / len(ours_k), "pct_mirror_in_ours": len(both) / len(m_k),
    }


def spot_check_sample(trades: pd.DataFrame, n: int = 50, seed: int = 7) -> pd.DataFrame:
    """Stratified sample (half House, half Senate, spread over years) to verify by hand."""
    t = trades.assign(year=trades.tx_date.dt.year)
    parts = []
    for chamber, g in t.groupby("chamber"):
        k = n // 2
        parts.append(g.groupby("year", group_keys=False)
                      .apply(lambda x: x.sample(min(len(x), max(1, k // g.year.nunique() + 1)), random_state=seed))
                      .sample(k, random_state=seed))
    s = pd.concat(parts)
    cols = ["chamber", "member", "source_url", "filing_date", "tx_date", "owner", "ticker",
            "asset_name", "side", "amount_raw"]
    s = s[cols].reset_index(drop=True)
    s["matches_filing (Y/N)"] = ""
    s["field_wrong"] = ""
    s["notes"] = ""
    s.to_csv(PROCESSED / "spot_check_50.csv", index_label="check_id")
    return s
