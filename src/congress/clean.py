"""Turn raw House and Senate PTR rows into one clean table of common-stock trades.

Every exclusion is counted in a waterfall (data/processed/cleaning_waterfall.csv)
so coverage losses can be reported rather than hidden.
"""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

from .config import INTERIM, PROCESSED, RAW, START_YEAR

HOUSE_PDF_URL = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc}.pdf"

# Standard disclosure brackets: lower bound -> upper bound.
BRACKETS = {
    1_001: 15_000, 15_001: 50_000, 50_001: 100_000, 100_001: 250_000,
    250_001: 500_000, 500_001: 1_000_000, 1_000_001: 5_000_000,
    5_000_001: 25_000_000, 25_000_001: 50_000_000,
}
NON_STOCK_WORDS = re.compile(
    r"\b(?:call|calls|put|puts|options?|notes?|bonds?|debentures?|treas\w*|municipal|"
    r"etf|fund|index|warrants?|preferred|pfd)\b|%",
    re.I,
)
SIDE = {
    "P": "buy", "Purchase": "buy",
    "S": "sell", "S (partial)": "sell", "Sale (Full)": "sell", "Sale (Partial)": "sell",
    "E": "exchange", "Exchange": "exchange",
}
OWNER = {"SP": "Spouse", "JT": "Joint", "DC": "Child"}


def parse_amount(s) -> tuple[float, float]:
    """'$1,001 - $15,000' -> (1001, 15000); 'Over $X' and exact values -> (X, X)."""
    if not isinstance(s, str):
        return np.nan, np.nan
    nums = [float(x.replace(",", "")) for x in re.findall(r"\$([\d,]+(?:\.\d+)?)", s)]
    if not nums:
        return np.nan, np.nan
    lo = nums[0]
    if len(nums) >= 2 and nums[1] >= lo:
        return lo, nums[1]
    if "-" in s and lo in BRACKETS:  # range whose upper half was lost on a line wrap
        return lo, float(BRACKETS[lo])
    return lo, lo


def _norm_name(s: str) -> str:
    s = str(s).split(",")[0].lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", s)
    return re.sub(r"[^a-z ]", "", s).strip()


def _load_terms() -> pd.DataFrame:
    rows = []
    for fn in ("legislators-historical.json", "legislators-current.json"):
        for p in json.loads((RAW / fn).read_text(encoding="utf-8")):
            n = p["name"]
            for t in p["terms"]:
                if t["end"] < "2013-01-01":
                    continue
                rows.append({
                    "bioguide": p["id"]["bioguide"], "last": _norm_name(n["last"]),
                    "first": n.get("first", "").lower(), "nick": n.get("nickname", "").lower(),
                    "full": n.get("official_full", ""), "chamber": "Senate" if t["type"] == "sen" else "House",
                    "state": t["state"], "district": t.get("district"), "party": t.get("party"),
                    "start": pd.Timestamp(t["start"]), "end": pd.Timestamp(t["end"]),
                })
    return pd.DataFrame(rows)


def attach_party(df: pd.DataFrame) -> pd.DataFrame:
    """Match each trade to a legislator term active on the transaction date."""
    terms = _load_terms()
    out = []
    for key, g in df.groupby(["chamber", "last_name", "first_name", "state_dst"], dropna=False):
        chamber, last, first, sd = key
        cand = terms[(terms.chamber == chamber) & (terms["last"] == _norm_name(last))]
        if chamber == "House" and isinstance(sd, str) and len(sd) >= 3:
            by_seat = cand[(cand.state == sd[:2]) & (cand.district == int(sd[2:] or 0))]
            cand = by_seat if len(by_seat) else cand[cand.state == sd[:2]]
        if cand.bioguide.nunique() > 1 and isinstance(first, str):
            f = first.lower().split()[0] if first.split() else ""
            narrowed = cand[(cand["first"].str.startswith(f[:3])) | (cand.nick.str.startswith(f[:3]))]
            cand = narrowed if len(narrowed) else cand
        g = g.copy()
        if cand.empty:
            g["bioguide"], g["party"], g["member"] = None, None, (f"{first} {last}").strip()
        else:
            # Party on the transaction date (handles the few mid-career switches).
            def pick(d):
                live = cand[(cand.start <= d) & (cand.end >= d)]
                return (live if len(live) else cand).iloc[-1]
            picked = g.tx_date.map(pick)
            g["bioguide"] = [p.bioguide for p in picked]
            g["party"] = [p.party for p in picked]
            g["member"] = [p.full or f"{first} {last}" for p in picked]
        out.append(g)
    return pd.concat(out)


def _house() -> pd.DataFrame:
    raw = pd.read_csv(INTERIM / "house_transactions_raw.csv", dtype=str)
    idx = pd.read_csv(INTERIM / "house_filings.csv", dtype=str)[["DocID", "Year"]]
    raw = raw.merge(idx, left_on="doc_id", right_on="DocID", how="left")
    status = raw.block.str.extract(r"(?i)S(?:TATUS)?\s*:\s*(New|Amended)", expand=False).str.title()
    # The parsed asset text still carries the row's dates, amounts, tags and checkbox glyphs.
    asset = (raw.asset.fillna("")
             .str.replace(r"\d{1,2}/\d{1,2}/\d{4}|\$[\d,.]+|\bgfedcb?\b|\[[A-Za-z]{2}\]|\(partial\)|\s-\s", " ", regex=True)
             .str.replace(r"^(?i:SP|JT|DC)\s+", "", regex=True)
             .str.split().str.join(" "))
    return pd.DataFrame({
        "chamber": "House",
        "first_name": raw.first_name, "last_name": raw.last_name, "state_dst": raw.state_dst,
        "doc_id": raw.doc_id,
        "source_url": [HOUSE_PDF_URL.format(year=y, doc=d) for y, d in zip(raw.Year, raw.doc_id)],
        "filing_date": raw.filing_date, "tx_date": raw.transaction_date,
        "owner": raw.owner.map(lambda o: OWNER.get(o, o)),
        "ticker": raw.ticker, "asset_name": asset, "asset_type": raw.asset_code,
        "tx_type": raw.type, "amount_raw": raw.amount,
        "description": raw.description, "amended": status.eq("Amended"),
    })


def _senate() -> pd.DataFrame:
    raw = pd.read_csv(INTERIM / "senate_transactions_raw.csv", dtype=str)
    return pd.DataFrame({
        "chamber": "Senate",
        "first_name": raw.first_name, "last_name": raw.last_name, "state_dst": None,
        "doc_id": raw.doc_id, "source_url": raw.url,
        "filing_date": raw.filing_date, "tx_date": raw["Transaction Date"],
        "owner": raw.Owner, "ticker": raw.Ticker.replace("--", np.nan),
        "asset_name": raw["Asset Name"], "asset_type": raw["Asset Type"],
        "tx_type": raw.Type, "amount_raw": raw.Amount,
        "description": raw.Comment, "amended": raw.title.str.contains("Amendment", na=False),
    })


def build() -> pd.DataFrame:
    """Raw rows -> cleaned common-stock trades. Writes the trades and a waterfall."""
    df = pd.concat([_house(), _senate()], ignore_index=True)
    steps = [("raw transaction rows", len(df))]

    def keep(mask, label):
        nonlocal df
        df = df[mask]
        steps.append((label, len(df)))

    df["side"] = df.tx_type.map(SIDE)
    keep(df.side.isin(["buy", "sell"]), "drop exchanges / unknown type")

    # Stocks only: the filer's asset tag where one exists (House [ST], Senate
    # 'Stock'); otherwise require a ticker and no option/bond/fund wording.
    tagged_stock = df.asset_type.isin(["ST", "Stock"])
    untagged = df.asset_type.isna()
    text = df.asset_name.fillna("") + " " + df.description.fillna("")
    keep((tagged_stock | untagged) & ~text.str.contains(NON_STOCK_WORDS), "drop options, bonds, funds, other non-stock")

    df["ticker"] = df.ticker.str.upper().str.strip().str.replace(r"[^A-Z.\-]", "", regex=True)
    keep(df.ticker.str.len().between(1, 6), "drop rows with no usable ticker")

    df["tx_date"] = pd.to_datetime(df.tx_date, format="mixed", errors="coerce")
    df["filing_date"] = pd.to_datetime(df.filing_date, format="mixed", errors="coerce")
    df["delay_days"] = (df.filing_date - df.tx_date).dt.days
    keep(df.tx_date.notna() & df.filing_date.notna(), "drop unparseable dates")
    keep(df.delay_days.between(0, 3 * 365), "drop impossible dates (filed before trade or >3y late)")
    keep(df.tx_date >= pd.Timestamp(f"{START_YEAR}-01-01"), f"drop trades before {START_YEAR}")

    lohi = df.amount_raw.map(parse_amount)
    df["amount_low"] = [a for a, _ in lohi]
    df["amount_high"] = [b for _, b in lohi]
    df["amount_mid"] = (df.amount_low + df.amount_high) / 2
    keep(df.amount_low.notna(), "drop unparseable amounts")

    df = attach_party(df)

    # Amended filings repeat the original's rows. A copier could only act on the
    # first disclosure, so keep the earliest filing of each identical trade.
    key = ["chamber", "last_name", "first_name", "ticker", "tx_date", "side", "amount_raw", "owner"]
    df = df.sort_values(["filing_date", "amended"]).drop_duplicates(key, keep="first")
    steps.append(("drop duplicate rows (amendments / repeated lines)", len(df)))

    df = df.reset_index(drop=True)
    df.to_parquet(PROCESSED / "trades_stage1.parquet")
    pd.DataFrame(steps, columns=["step", "rows_remaining"]).to_csv(PROCESSED / "cleaning_waterfall.csv", index=False)
    return df


if __name__ == "__main__":
    d = build()
    print(pd.read_csv(PROCESSED / "cleaning_waterfall.csv").to_string(index=False))
    print(d.groupby(["chamber", "side"]).size())
    print(d.party.value_counts(dropna=False))
