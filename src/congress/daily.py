"""Daily update: new filings, fresh prices and news, rebuilt site data and picks.

    python -m congress.daily

Run by .github/workflows/daily.yml. Filing and price caches persist between
runs (GitHub Actions cache), so a normal day only downloads what is new.
The full study (factor regressions, figures) is refreshed once a month,
when the Ken French factor files publish a new month.
"""
from __future__ import annotations

import time

import pandas as pd

from . import clean, dataset, other_assets, prices, recs, scrape_house, scrape_senate, site_data, study
from .config import PROCESSED
from .factors import load_factors


def step(name, fn, *a, **k):
    t = time.time()
    print(f"==> {name}", flush=True)
    out = fn(*a, **k)
    print(f"    done in {time.time() - t:.0f}s", flush=True)
    return out


def main() -> None:
    step("Senate filings", scrape_senate.run)
    step("House filings", scrape_house.run)
    step("Clean trades", clean.build)
    stage1 = pd.read_parquet(PROCESSED / "trades_stage1.parquet")
    syms = sorted(set(stage1.ticker.map(prices.yf_symbol)) | {"SPY"})
    step("Prices for new tickers", prices.download, syms, threads=2)
    step("Price-side filters", dataset.build)

    # Fresh prices for anything traded in the last ~13 months (features, outcomes, sizing).
    t = pd.read_parquet(PROCESSED / "trades.parquet")
    active = t[t.filing_date > pd.Timestamp.today() - pd.Timedelta(days=400)].symbol
    n = step("Refresh active prices", prices.refresh, sorted(set(active) | {"SPY"}))
    print(f"    {n} symbols refreshed", flush=True)

    step("Non-stock trades", other_assets.build)

    # New factor month -> rerun the study (regressions, robustness) for the public pages.
    # The Ken French server is slow and sometimes unreachable; the cached file is fine for a day.
    old_end = load_factors().index.max()
    try:
        new_end = step("Factor data", load_factors, refresh=True).index.max()
    except Exception as e:  # noqa: BLE001
        print(f"    factor refresh failed ({type(e).__name__}); keeping cached factors through {old_end.date()}", flush=True)
        new_end = old_end
    if new_end > old_end:
        step("Study (new factor month)", study.main)

    step("Site data", site_data.main)
    out = step("Picks", recs.build, asof=pd.Timestamp.today().normalize())
    print(f"    picks as of {out['asof']}: {out['counts']} (validated={out['model']['validated']})", flush=True)


if __name__ == "__main__":
    main()
