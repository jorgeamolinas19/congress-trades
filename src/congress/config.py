"""Paths and study-wide constants."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"

START_YEAR = 2014
END_YEAR = __import__('datetime').date.today().year

USER_AGENT = "Mozilla/5.0 (academic research; congress-trades replication)"

for _p in (RAW, INTERIM, PROCESSED, FIGURES):
    _p.mkdir(parents=True, exist_ok=True)
