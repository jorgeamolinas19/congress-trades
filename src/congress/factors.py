"""Daily Fama-French 5 factors plus momentum from the Ken French Data Library."""
from __future__ import annotations

import io
import zipfile

import pandas as pd
import requests

from .config import RAW

BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FILES = {
    "ff5": "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip",
    "mom": "F-F_Momentum_Factor_daily_CSV.zip",
}


def _read_french_csv(path) -> pd.DataFrame:
    """Parse a Ken French CSV: prose header, then a date-indexed table in percent."""
    with zipfile.ZipFile(path) as z:
        text = z.read(z.namelist()[0]).decode("latin-1")
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(","))
    body = [lines[start]]
    for l in lines[start + 1:]:
        if not l.strip() or not l.strip()[0].isdigit():
            break
        body.append(l)
    df = pd.read_csv(io.StringIO("\n".join(body)), index_col=0)
    df.index = pd.to_datetime(df.index.astype(str), format="%Y%m%d")
    df.columns = [c.strip() for c in df.columns]
    return df / 100.0


def _download(url: str, path) -> None:
    """Fetch a Ken French zip, replacing the cached copy only if the response
    really is a zip file (the server sometimes answers with an HTML error page)."""
    r = requests.get(url, timeout=120)
    if r.status_code != 200 or not r.content.startswith(b"PK"):
        if path.exists():
            return
        raise RuntimeError(f"factor download failed: {url} -> {r.status_code}")
    path.write_bytes(r.content)


def load_factors(refresh: bool = False) -> pd.DataFrame:
    """Daily factor returns as decimals: Mkt-RF, SMB, HML, RMW, CMA, Mom, RF."""
    frames = []
    for name in ("ff5", "mom"):
        path = RAW / FILES[name]
        if refresh or not path.exists():
            _download(BASE + FILES[name], path)
        frames.append(_read_french_csv(path))
    return frames[0].join(frames[1], how="inner")
