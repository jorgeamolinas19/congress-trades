"""Scrape Periodic Transaction Reports (PTRs) from the Senate eFD site.

Electronic PTRs are HTML tables and are parsed here. Paper PTRs are scanned
images; they are logged (so coverage loss can be reported) but not parsed.
Raw HTML is cached under data/raw/senate/ so re-runs are free.
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .config import END_YEAR, INTERIM, RAW, START_YEAR, USER_AGENT

BASE = "https://efdsearch.senate.gov"
CACHE = RAW / "senate"
CACHE.mkdir(parents=True, exist_ok=True)
PTR_REPORT_TYPE = "[11]"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    r = s.get(f"{BASE}/search/home/", timeout=60)
    tok = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text).group(1)
    s.post(
        f"{BASE}/search/home/",
        data={"prohibition_agreement": "1", "csrfmiddlewaretoken": tok},
        headers={"Referer": f"{BASE}/search/home/"},
        timeout=60,
    )
    return s


def list_filings(s: requests.Session, year: int) -> list[dict]:
    """All PTR filings submitted in a calendar year (electronic and paper)."""
    out, start = [], 0
    while True:
        csrf = s.cookies.get("csrftoken")
        r = s.post(
            f"{BASE}/search/report/data/",
            data={
                "start": start, "length": 100, "report_types": PTR_REPORT_TYPE,
                "filer_types": "[]", "first_name": "", "last_name": "",
                "submitted_start_date": f"01/01/{year} 00:00:00",
                "submitted_end_date": f"12/31/{year} 23:59:59",
                "candidate_state": "", "senator_state": "", "office_id": "",
                "csrfmiddlewaretoken": csrf,
            },
            headers={"Referer": f"{BASE}/search/", "X-CSRFToken": csrf},
            timeout=60,
        )
        j = r.json()
        for first, last, office, link, filed in j["data"]:
            href = re.search(r'href="([^"]+)"', link).group(1)
            title = BeautifulSoup(link, "lxml").get_text(strip=True)
            out.append({
                "first_name": first.strip(), "last_name": last.strip(), "office": office,
                "url": BASE + href, "doc_id": href.rstrip("/").split("/")[-1],
                "kind": "paper" if "/paper/" in href else "ptr",
                "title": title, "filing_date": filed,
            })
        start += 100
        if start >= j["recordsTotal"]:
            return out


def _fetch(s: requests.Session, f: dict) -> str | None:
    path = CACHE / f"{f['doc_id']}.html"
    if path.exists():
        return path.read_text(encoding="utf-8")
    for attempt in range(4):
        try:
            r = s.get(f["url"], timeout=60)
            if r.status_code == 200 and "Transaction Date" in r.text:
                path.write_text(r.text, encoding="utf-8")
                return r.text
        except requests.RequestException:
            pass
        time.sleep(2 ** attempt)
    return None


def parse_ptr(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None:
        return []
    heads = [th.get_text(strip=True) for th in table.find_all("th")]
    rows = []
    for tr in table.find("tbody").find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) == len(heads):
            rows.append(dict(zip(heads, cells)))
    return rows


def run() -> pd.DataFrame:
    s = _session()
    filings = []
    for y in range(START_YEAR, END_YEAR + 1):
        fs = list_filings(s, y)
        print(f"senate {y}: {len(fs)} PTR filings ({sum(f['kind'] == 'paper' for f in fs)} paper)")
        filings += fs
    pd.DataFrame(filings).to_csv(INTERIM / "senate_filings.csv", index=False)

    electronic = [f for f in filings if f["kind"] == "ptr"]
    with ThreadPoolExecutor(4) as ex:
        htmls = list(ex.map(lambda f: _fetch(s, f), electronic))

    rows = []
    for f, html in zip(electronic, htmls):
        if html is None:
            continue
        for t in parse_ptr(html):
            rows.append({**{k: f[k] for k in ("first_name", "last_name", "doc_id", "title", "filing_date", "url")}, **t})
    df = pd.DataFrame(rows)
    df.to_csv(INTERIM / "senate_transactions_raw.csv", index=False)
    print(f"senate: {len(df)} transaction rows from {df.doc_id.nunique()} electronic PTRs")
    return df


if __name__ == "__main__":
    run()
