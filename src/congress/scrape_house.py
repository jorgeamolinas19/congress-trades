"""Scrape Periodic Transaction Reports from the House Clerk disclosure site.

The yearly index zip ({year}FD.zip) lists every filing; FilingType 'P' is a PTR.
Electronically filed PTRs (DocID starting with '2') are text PDFs and parsed
here. Scanned paper PTRs are image-only; they are counted, not parsed.
"""
from __future__ import annotations

import io
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import pdfplumber
import requests

from .config import END_YEAR, INTERIM, RAW, START_YEAR, USER_AGENT

BASE = "https://disclosures-clerk.house.gov/public_disc"
CACHE = RAW / "house_pdfs"
INDEX = RAW / "house_index"
CACHE.mkdir(parents=True, exist_ok=True)
INDEX.mkdir(parents=True, exist_ok=True)

_DATE = r"\d{1,2}/\d{1,2}/\d{4}"
_MONEY = r"\$[\d,]+(?:\.\d+)?"
# One transaction: [owner] asset ... tx-type  tx-date  notification-date  amount.
# The amount range can wrap onto the next line, with the asset-type tag
# (e.g. "[ST]") and description fragments printed in between. Older PDFs embed
# fonts that garble letter case ("sP", "[sT]", "(aXP)"), so matching ignores case.
TX_RE = re.compile(
    rf"^(?:(?P<owner>SP|JT|DC)\s+)?(?P<asset>.+?)\s+"
    rf"(?P<type>S \(partial\)|P|S|E)\s+(?P<tdate>{_DATE})\s+(?P<ndate>{_DATE})\s+"
    rf"(?P<amt>(?:{_MONEY}\s*-\s*(?:{_MONEY})?|Over {_MONEY}|{_MONEY}))",
    re.M | re.I,
)
TICKER_RE = re.compile(r"\(([A-Za-z][A-Za-z.\-]{0,6})\)")
TAG_RE = re.compile(r"\[([A-Za-z]{2})\]")
STATUS_RE = re.compile(r"F(?:ILING)?\s*S(?:TATUS)?\s*:", re.I)


def load_index(year: int) -> pd.DataFrame:
    path = INDEX / f"{year}FD.zip"
    # Recent years' indexes grow daily (and late filings land in the prior
    # year's index), so re-download those once they're more than 12 hours old.
    stale = year >= END_YEAR - 1 and path.exists() and time.time() - path.stat().st_mtime > 12 * 3600
    if not path.exists() or stale:
        r = requests.get(f"{BASE}/financial-pdfs/{year}FD.zip", timeout=120,
                         headers={"User-Agent": USER_AGENT})
        path.write_bytes(r.content)
    with zipfile.ZipFile(path) as z:
        df = pd.read_csv(z.open(f"{year}FD.txt"), sep="\t", dtype=str)
    df["Year"] = year
    return df[df.FilingType == "P"]


def _fetch(year: int, doc: str) -> bytes | None:
    path = CACHE / f"{doc}.pdf"
    if path.exists():
        return path.read_bytes()
    for attempt in range(4):
        try:
            r = requests.get(f"{BASE}/ptr-pdfs/{year}/{doc}.pdf", timeout=60,
                             headers={"User-Agent": USER_AGENT})
            if r.status_code == 200 and r.content[:4] == b"%PDF":
                path.write_bytes(r.content)
                return r.content
        except requests.RequestException:
            pass
        time.sleep(2 ** attempt)
    return None


PARSED = INTERIM / "house_parsed"
PARSED.mkdir(parents=True, exist_ok=True)
PARSER_VERSION = 3  # bump when parse_ptr_text changes, to re-parse every cached PDF


def parse_cached(doc: str, content: bytes) -> list[dict]:
    """Parsed transactions for one PDF, cached as JSON keyed by parser version."""
    import json
    path = PARSED / f"{doc}.json"
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached.get("v") == PARSER_VERSION:
            return cached["rows"]
    rows = parse_ptr_text(pdf_text(content))
    path.write_text(json.dumps({"v": PARSER_VERSION, "rows": rows}), encoding="utf-8")
    return rows


def pdf_text(content: bytes) -> str:
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    return text.replace("\x00", "")


def parse_ptr_text(text: str) -> list[dict]:
    """Extract transactions from the text of an electronic House PTR."""
    matches = list(TX_RE.finditer(text))
    rows = []
    for i, m in enumerate(matches):
        # The block for this transaction runs until the next transaction starts;
        # wrapped amount halves, asset tags and description lines live there.
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[m.start():end]
        amt = m.group("amt").strip()
        if amt.endswith("-"):  # range wrapped onto the following line
            # The next dollar figure is usually the upper bound, but can be the
            # "Cap. Gains > $200?" column header; only a larger value qualifies.
            lo = float(re.sub(r"[$,]", "", amt.rstrip("- ")))
            for nxt in re.finditer(_MONEY, block[m.end() - m.start():]):
                if float(re.sub(r"[$,]", "", nxt.group(0))) > lo:
                    amt = f"{amt} {nxt.group(0)}"
                    break
        # Asset name, ticker and tag all sit before the "FILING STATUS" line.
        status = STATUS_RE.search(block)
        asset_part = block[: status.start()] if status else block[:400]
        # The transaction-type "(partial)" is also parenthesised; it is not a ticker.
        tick = [t for t in TICKER_RE.findall(asset_part) if t.lower() != "partial"]
        tag = TAG_RE.findall(asset_part)
        desc = re.search(r"D(?:ESCRIPTION)?:\s*(.+)", block, re.I)
        rows.append({
            "owner": m.group("owner").upper() if m.group("owner") else "Self",
            "asset": " ".join(asset_part.split()),
            "ticker": tick[-1].upper() if tick else None,
            "asset_code": tag[0].upper() if tag else None,
            "type": m.group("type").upper().replace("(PARTIAL)", "(partial)"),
            "transaction_date": m.group("tdate"),
            "notification_date": m.group("ndate"),
            "amount": amt,
            "description": desc.group(1).strip() if desc else None,
            "block": block[:600],
        })
    return rows


def run(cached_only: bool = False) -> pd.DataFrame:
    """Download (unless cached_only) and parse every electronic House PTR."""
    idx = pd.concat([load_index(y) for y in range(START_YEAR, END_YEAR + 1)])
    idx["electronic"] = idx.DocID.str.startswith("2")
    idx.to_csv(INTERIM / "house_filings.csv", index=False)
    print(idx.groupby("Year").electronic.agg(["size", "sum"]).rename(columns={"size": "ptrs", "sum": "electronic"}))

    el = idx[idx.electronic]
    if cached_only:
        el = el[[(CACHE / f"{d}.pdf").exists() for d in el.DocID]]
    with ThreadPoolExecutor(6) as ex:
        contents = list(ex.map(lambda r: _fetch(r[0], r[1]), zip(el.Year, el.DocID)))

    rows, status = [], []
    for (_, f), content in zip(el.iterrows(), contents):
        if content is None:
            status.append((f.DocID, "download_failed", 0))
            continue
        try:
            txs = parse_cached(f.DocID, content)
        except Exception as e:  # malformed PDF
            status.append((f.DocID, f"parse_error:{type(e).__name__}", 0))
            continue
        status.append((f.DocID, "ok" if txs else "no_transactions_found", len(txs)))
        for t in txs:
            rows.append({"doc_id": f.DocID, "first_name": f.First, "last_name": f.Last,
                         "state_dst": f.StateDst, "filing_date": f.FilingDate, **t})
    pd.DataFrame(status, columns=["doc_id", "status", "n_tx"]).to_csv(INTERIM / "house_parse_status.csv", index=False)
    df = pd.DataFrame(rows)
    df.to_csv(INTERIM / "house_transactions_raw.csv", index=False)
    print(f"house: {len(df)} transaction rows from {df.doc_id.nunique()} PDFs")
    return df


if __name__ == "__main__":
    import sys
    run(cached_only="--cached-only" in sys.argv)
