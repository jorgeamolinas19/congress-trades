"""Non-stock trades: options, bonds, funds/ETFs, crypto and private holdings.

The study analyzes common stock only. This module keeps the rows the stock
filter set aside, classifies them, and parses option details (call/put,
strike, expiry) so the website can list them. Only funds/ETFs get a
performance figure: free price history does not exist for individual option
contracts or most bonds.

    python -m congress.other_assets
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import clean, prices
from .config import PROCESSED, START_YEAR

OPTIONS, BONDS, FUNDS, CRYPTO, OTHER = "Options", "Bonds & Treasuries", "Funds & ETFs", "Crypto", "Private & other"

# Filer asset-type codes (House codes per fd.house.gov/reference/asset-type-codes).
CODE_CLASS = {
    "OP": OPTIONS, "SA": OPTIONS, "Stock Option": OPTIONS,
    "GS": BONDS, "CS": BONDS, "AB": BONDS, "Municipal Security": BONDS, "Corporate Bond": BONDS,
    "EF": FUNDS, "ET": FUNDS, "MF": FUNDS,
    "CT": CRYPTO, "Cryptocurrency": CRYPTO,
    "HN": OTHER, "PS": OTHER, "OI": OTHER, "OL": OTHER, "VA": OTHER, "RS": OTHER,
    "Non-Public Stock": OTHER, "Commodities/Futures Contract": OTHER,
}
TEXT_RULES = [
    (OPTIONS, re.compile(r"\b(?:calls?|puts?|options?|strike)\b", re.I)),
    (BONDS, re.compile(r"\b(?:bonds?|notes?|debentures?|treas\w*|municipal|t-bill|bills?)\b|%", re.I)),
    (FUNDS, re.compile(r"\b(?:etf|fund|index|spdr|ishares|vanguard|invesco|proshares|trust)\b", re.I)),
    (CRYPTO, re.compile(r"\b(?:bitcoin|ethereum|crypto\w*)\b", re.I)),
]

OPT_TYPE = re.compile(r"\b(call|put)s?\b", re.I)
_NUM = r"([\d,]*\d(?:\.\d+)?)"
# Tried in order: "Strike price: $210", "@ 285", "$175 EXP", "put 180.000", "124.5 CALL".
# "put 180" goes before "124.5 CALL" so "SPY Feb 2016 put 180" doesn't read the year as the strike.
OPT_STRIKES = [re.compile(p, re.I) for p in (
    rf"strike\s*(?:price)?:?\s*(?:of\s*)?\$?\s*{_NUM}", rf"@\s*\$?\s*{_NUM}", rf"\${_NUM}",
    rf"\b(?:calls?|puts?)\s+{_NUM}\b", rf"\b{_NUM}\s+(?:calls?|puts?)\b")]
OPT_EXPIRY = re.compile(r"(?:\bexp\w*\.?(?:\s+date)?(?:\s+of)?)\s*:?\s*(\d{1,2}/\d{1,2}/\d{2,4})", re.I)
OPT_EXPIRY_MONTH = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\.?\s+(20\d\d)\b", re.I)
OPT_CONTRACTS = re.compile(r"\b(\d[\d,]*)\s+(?:call\s+|put\s+)?(?:option|contract)s?\b", re.I)


def classify(code, text: str) -> str:
    """Asset class from the filer's code, falling back to the asset text."""
    if isinstance(code, str) and code in CODE_CLASS:
        return CODE_CLASS[code]
    for cls, rx in TEXT_RULES:
        if rx.search(text):
            return cls
    return OTHER


def option_detail(text: str) -> dict:
    """Call/put, strike, expiry and contract count, where the filing states them."""
    t = OPT_TYPE.search(text)
    s = next((m for rx in OPT_STRIKES if (m := rx.search(text))), None)
    e = OPT_EXPIRY.search(text)
    em = None if e else OPT_EXPIRY_MONTH.search(text)
    n = OPT_CONTRACTS.search(text)
    return {
        "option_type": t.group(1).title() if t else None,
        "strike": float(s.group(1).replace(",", "")) if s else None,
        "expiry": e.group(1) if e else (f"{em.group(1).title()} {em.group(2)}" if em else None),
        "contracts": int(n.group(1).replace(",", "")) if n else None,
    }


def _clean_name(name: str) -> str:
    """Strip House DocID prefixes, the trailing P/S type letter, tickers and option boilerplate."""
    s = str(name or "")
    s = re.split(r"Option Type:|\bID Owner Asset", s, flags=re.I)[0]
    s = re.sub(r"^\d{6,}\s+", "", s)
    s = re.sub(r"\([A-Za-z.\-]{1,6}\)|\[[A-Za-z]{2}\]", " ", s)
    s = re.sub(r"\s+[PS]\s*$", "", s.strip())
    return " ".join(s.split())[:90]


def build() -> pd.DataFrame:
    df = pd.concat([clean._house(), clean._senate()], ignore_index=True)
    df["side"] = df.tx_type.map(clean.SIDE)
    df = df[df.side.isin(["buy", "sell"])]

    # Exactly the complement of the stock filter in clean.build().
    tagged = df.asset_type.isin(["ST", "Stock"])
    untagged = df.asset_type.isna()
    text = df.asset_name.fillna("") + " " + df.description.fillna("")
    is_stock = (tagged | untagged) & ~text.str.contains(clean.NON_STOCK_WORDS)
    df, text = df[~is_stock].copy(), text[~is_stock]
    df["asset_class"] = [classify(c, t) for c, t in zip(df.asset_type, text)]

    df["tx_date"] = pd.to_datetime(df.tx_date, format="mixed", errors="coerce")
    df["filing_date"] = pd.to_datetime(df.filing_date, format="mixed", errors="coerce")
    df["delay_days"] = (df.filing_date - df.tx_date).dt.days
    df = df[df.delay_days.between(0, 3 * 365) & (df.tx_date >= pd.Timestamp(f"{START_YEAR}-01-01"))]
    lohi = df.amount_raw.map(clean.parse_amount)
    df["amount_low"] = [a for a, _ in lohi]
    df["amount_high"] = [b for _, b in lohi]
    df["amount_mid"] = (df.amount_low + df.amount_high) / 2
    df["ticker"] = df.ticker.str.upper().str.strip().str.replace(r"[^A-Z.\-]", "", regex=True).replace("", np.nan)

    opt = [option_detail(f"{a} {d}") if c == OPTIONS else {}
           for a, d, c in zip(df.asset_name.fillna(""), df.description.fillna(""), df.asset_class)]
    df = df.join(pd.DataFrame(opt, index=df.index))
    df["asset_name"] = df.asset_name.map(_clean_name)
    df = clean.attach_party(df)
    key = ["chamber", "last_name", "first_name", "ticker", "asset_name", "tx_date", "side", "amount_raw", "owner"]
    df = df.sort_values(["filing_date", "amended"]).drop_duplicates(key, keep="first")

    # Stocks the price step later identified as ETFs or mutual funds belong here too.
    stage1 = pd.read_parquet(PROCESSED / "trades_stage1.parquet")
    meta = prices.load_meta().set_index("symbol")
    sym = stage1.ticker.map(prices.yf_symbol)
    funds = stage1[sym.map(meta.instrument_type).isin(["ETF", "MUTUALFUND"])].copy()
    funds["asset_class"] = FUNDS
    df = pd.concat([df, funds], ignore_index=True)

    df["description"] = df.description.where(df.description.ne("--"))
    cols = ["chamber", "member", "party", "bioguide", "first_name", "last_name", "state_dst", "doc_id",
            "source_url", "filing_date", "tx_date", "delay_days", "owner", "ticker", "asset_name",
            "asset_class", "side", "amount_raw", "amount_low", "amount_high", "amount_mid", "description",
            "option_type", "strike", "expiry", "contracts"]
    df = df[cols].reset_index(drop=True)
    df.to_parquet(PROCESSED / "other_trades.parquet")
    return df


if __name__ == "__main__":
    d = build()
    print(len(d), "non-stock trades")
    print(d.asset_class.value_counts())
    o = d[d.asset_class == OPTIONS]
    print("options with type/strike/expiry parsed:",
          o.option_type.notna().mean().round(3), o.strike.notna().mean().round(3), o.expiry.notna().mean().round(3))
    print(d[d.member.str.contains("Pelosi", na=False)].asset_class.value_counts())
