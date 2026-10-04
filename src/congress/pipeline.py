"""End-to-end reproduction.

    python -m congress.pipeline            # everything (downloads are cached)
    python -m congress.pipeline --offline  # skip scraping; re-parse cached filings
"""
from __future__ import annotations

import json
import sys

import pandas as pd

from . import clean, dataset, plots, prices, scrape_house, scrape_senate, study, validate
from .config import PROCESSED


def main(offline: bool = False) -> None:
    if not offline:
        scrape_senate.run()
    scrape_house.run(cached_only=offline)
    clean.build()
    d = dataset.build()
    # Second, slow pass over anything yfinance failed on, so throttling isn't
    # mistaken for delisting; then re-apply the price filters.
    prices.download(sorted(set(d.symbol) | set(pd.read_parquet(PROCESSED / "trades_stage1.parquet")
                                                 .ticker.map(prices.yf_symbol))),
                    retry_failed=True, threads=2)
    d = dataset.build()
    xc = validate.senate_crosscheck(d)
    (PROCESSED / "senate_crosscheck.json").write_text(json.dumps(xc, indent=2))
    validate.spot_check_sample(d)
    study.main()
    plots.all_figures()


if __name__ == "__main__":
    main(offline="--offline" in sys.argv)
