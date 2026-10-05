"""Buy / don't-buy recommendations for recent disclosures, with a confidence.

    python -m congress.recs            # backtest + score recent disclosures

The model is a logistic regression on features known at the decision date:

  member_odds   the member's past copy hit rate, shrunk for luck, using only
                filings whose 6-month outcome had finished by that date
  runup         stock return minus SPY from the member's trade date to entry
                (how much of any move a copier already missed)
  momentum      stock minus SPY over the 6 months before entry
  log_amount    log of the disclosed amount (range midpoint)
  log_delay     log(1 + days from trade to disclosure)
  crowd         other members who disclosed buying the same stock in the prior 30 days

Target: did the stock beat SPY over the 6 months after entry (the day after
disclosure). It is fitted on decisions before 2020-07 (so every training
outcome is known before the test period) and tested on 2021 onward. A "Buy"
is only ever issued if the top-scored group beat SPY out of sample with
t >= 2 (month-clustered). Otherwise everything is "Don't buy", and the page
says why.

Output goes to web/public/picks/recs.json, which is git-ignored and served
only behind the password middleware.
"""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd
import statsmodels.api as sm

from . import odds, prices
from .config import PROCESSED, ROOT

OUT = ROOT / "web" / "public" / "picks"
HOLD = 126
FEATURES = ["member_odds", "runup", "momentum", "log_amount", "log_delay", "crowd"]
TRAIN_END = pd.Timestamp("2020-07-01")
TEST_START = pd.Timestamp("2021-01-01")
RECENT_DAYS = 30          # disclosures from the last 30 days are actionable
LATE_FILING_DAYS = 45     # filed after the legal deadline: historically -4.7% vs SPY
TOP_SHARE = 0.2           # "Buy" = scores in the training set's top 20%


def _prices():
    px = pd.read_parquet(prices.PRICES_PATH).sort_index()
    return px, px["SPY"]


def features(buys: pd.DataFrame, px: pd.DataFrame, spy: pd.Series, asof: pd.Timestamp | None = None) -> pd.DataFrame:
    """Decision-time features (+ the outcome where it is known).

    `asof` scores live decisions: entry is the later of the day after
    disclosure and `asof`, so run-up and momentum use today's prices.
    """
    cal = px.index
    arr, sp = px.to_numpy(), spy.reindex(cal).to_numpy()
    col = px.columns.get_indexer(buys.symbol)
    t0 = np.minimum(cal.searchsorted(buys.tx_date.values), len(cal) - 1)
    i0 = cal.searchsorted(buys.filing_date.values) + 1
    if asof is not None:
        i0 = np.maximum(i0, cal.searchsorted(asof, side="right") - 1)
    i0 = np.minimum(i0, len(cal) - 1)
    rel = lambda a, b: arr[b, col] / arr[a, col] - sp[b] / sp[a]  # noqa: E731
    f = pd.DataFrame(index=buys.index)
    f["entry_date"] = cal[i0]
    f["runup"] = rel(t0, i0)
    f["momentum"] = rel(np.maximum(i0 - 126, 0), i0)
    f["log_amount"] = np.log(buys.amount_mid.clip(lower=1))
    f["log_delay"] = np.log1p(buys.delay_days)
    i1 = i0 + HOLD
    done = i1 < len(cal)
    f["excess_6m"] = np.where(done, rel(i0, np.minimum(i1, len(cal) - 1)), np.nan)
    ii = np.minimum(i1, len(cal) - 1)
    f["ret_6m"] = np.where(done, arr[ii, col] / arr[i0, col] - 1, np.nan)
    f["outcome_known"] = pd.Series(cal[np.minimum(i1, len(cal) - 1)], index=buys.index).where(done)
    return f


def add_crowd(buys: pd.DataFrame, pool: pd.DataFrame) -> pd.Series:
    """Distinct other members disclosing a buy of the same ticker in the prior 30 days."""
    p = pool[["ticker", "member", "filing_date"]]
    out = []
    for tk, g in buys.groupby("ticker"):
        q = p[p.ticker == tk]
        for idx, r in g.iterrows():
            w = q[(q.filing_date <= r.filing_date) & (q.filing_date > r.filing_date - pd.Timedelta(days=30)) & (q.member != r.member)]
            out.append((idx, w.member.nunique()))
    return pd.Series(dict(out)).reindex(buys.index).fillna(0)


def add_member_odds(df: pd.DataFrame, hist: pd.DataFrame, p: float, k: float, unit_var: float) -> pd.Series:
    """Point-in-time shrunk hit rate: only past filings whose outcome was known
    before this decision's entry date count."""
    won = hist.excess_6m > 0
    filings = (hist.assign(won=won).groupby(["member", "filing_date"])
               .agg(score=("won", "mean"), known=("outcome_known", "max")).reset_index())
    out = pd.Series(p, index=df.index, dtype=float)
    for m, g in df.groupby("member"):
        fm = filings[filings.member == m].sort_values("known")
        if fm.empty:
            continue
        known = fm.known.to_numpy()
        cum_n = np.arange(1, len(fm) + 1)
        cum_s = fm.score.cumsum().to_numpy()
        j = known.searchsorted(g.entry_date.to_numpy(), side="left")   # filings known strictly before entry
        n = np.where(j > 0, cum_n[np.maximum(j - 1, 0)], 0)
        rate = np.where(n > 0, cum_s[np.maximum(j - 1, 0)] / np.maximum(n, 1), p)
        out[g.index] = (n * rate + k * p) / (n + k)
    return out


def _clustered(x: pd.Series, month: pd.Series) -> tuple[float, float, int]:
    m = x.groupby(month).mean().dropna()
    return float(m.mean()), float(m.mean() / (m.std(ddof=1) / np.sqrt(len(m)))), int(len(m))


def _auc(score: np.ndarray, y: np.ndarray) -> float:
    r = pd.Series(score).rank().to_numpy()
    pos = y.astype(bool)
    return float((r[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * (~pos).sum()))


def fit(X: pd.DataFrame, y: pd.Series):
    mu, sd = X.mean(), X.std(ddof=0).replace(0, 1)
    model = sm.Logit(y.astype(float), sm.add_constant((X - mu) / sd)).fit(disp=0)
    predict = lambda Z: model.predict(sm.add_constant((Z[X.columns] - mu) / sd, has_constant="add"))  # noqa: E731
    return model, predict


def backtest(data: pd.DataFrame) -> dict:
    """Fit before TRAIN_END, test from TEST_START; report what a 'Buy' rule did."""
    train = data[(data.entry_date < TRAIN_END) & data.excess_6m.notna()]
    test = data[(data.entry_date >= TEST_START) & data.excess_6m.notna()]
    model, predict = fit(train[FEATURES], train.excess_6m > 0)
    cut = float(np.quantile(predict(train), 1 - TOP_SHARE))
    p_test = predict(test)
    buy = p_test >= cut
    month = test.entry_date.dt.to_period("M")
    top_mu, top_t, months = _clustered(test.excess_6m[buy], month[buy])
    rest_mu, rest_t, _ = _clustered(test.excess_6m[~buy], month[~buy])
    all_mu, all_t, _ = _clustered(test.excess_6m, month)
    # Calibration: predicted probability vs realized hit rate, by quintile.
    q = pd.qcut(p_test, 5, labels=False, duplicates="drop")
    calib = [{"predicted": float(p_test[q == i].mean()), "realized": float((test.excess_6m[q == i] > 0).mean()),
              "mean_excess_6m": float(test.excess_6m[q == i].mean()), "n": int((q == i).sum())} for i in sorted(set(q))]
    report = {
        "train": {"n": int(len(train)), "end": str(TRAIN_END.date())},
        "test": {"n": int(len(test)), "start": str(TEST_START.date()), "months": months},
        "coefficients": {k: {"coef": float(v), "t": float(model.tvalues[k])} for k, v in model.params.items()},
        "auc_test": _auc(p_test.to_numpy(), (test.excess_6m > 0).to_numpy()),
        "buy_threshold": cut,
        "buy_group": {"n": int(buy.sum()), "mean_excess_6m": top_mu, "t": top_t,
                      "hit_rate": float((test.excess_6m[buy] > 0).mean())},
        "rest": {"n": int((~buy).sum()), "mean_excess_6m": rest_mu, "t": rest_t,
                 "hit_rate": float((test.excess_6m[~buy] > 0).mean())},
        "all": {"mean_excess_6m": all_mu, "t": all_t, "hit_rate": float((test.excess_6m > 0).mean())},
        "calibration": calib,
        "validated": bool(top_mu > 0 and top_t >= 2.0),
    }
    return report, predict


def history() -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """All past stock buys with features, outcomes and point-in-time member odds."""
    px, spy = _prices()
    t = pd.read_parquet(PROCESSED / "trades.parquet")
    t = t[t.symbol.isin(px.columns)]
    buys = t[t.side == "buy"].copy()
    f = features(buys, px, spy)
    data = buys.join(f)
    data["crowd"] = add_crowd(data, buys)
    # Shrinkage settings from the training period only.
    tr = data[(data.entry_date < TRAIN_END) & data.excess_6m.notna()]
    per, unit_var = odds.filing_scores(tr.member, tr.filing_date, tr.excess_6m > 0)
    fitm = per[per.n >= 10]
    p0 = float((tr.excess_6m > 0).mean())
    k = odds.shrinkage_strength(fitm.rate.to_numpy(), fitm.n.to_numpy(float), unit_var)
    data["member_odds"] = add_member_odds(data, data[data.excess_6m.notna()], p0, k, unit_var)
    data.attrs.update(p0=p0, k=k, unit_var=unit_var)
    return data, px, spy


# --------------------------------------------------------------------------- #
# Live recommendations
# --------------------------------------------------------------------------- #
TAKEOVER = re.compile(r"\b(acquir\w*|acquisition|merger|merge|buyout|takeover|tender offer|"
                      r"go(?:es|ing)? private|take(?:s|n)? private|deal to buy|agrees? to buy)\b", re.I)


def _name_key(long_name: str | None) -> str | None:
    """First distinctive word of a company name: 'NVIDIA Corporation' -> 'nvidia'."""
    words = re.findall(r"[A-Za-z][A-Za-z&'.-]+", long_name or "")
    skip = {"the", "inc", "corp", "corporation", "co", "company", "group", "holdings"}
    words = [w.lower().strip(".") for w in words if w.lower().strip(".") not in skip]
    return words[0] if words and len(words[0]) >= 3 else None


def fetch_news(symbol: str, since: pd.Timestamp, limit: int = 3, long_name: str | None = None) -> list[dict]:
    """Recent headlines about this company, newest first. A headline counts if
    Yahoo tags the ticker AND the title names the company or the ticker;
    tagging alone pulls in market roundups that merely mention it."""
    key = _name_key(long_name)
    tick = re.compile(rf"(?<![A-Za-z]){re.escape(symbol)}(?![A-Za-z])") if len(symbol) >= 3 else None
    import yfinance as yf
    try:
        items = yf.Search(symbol, news_count=12).news
    except Exception:
        return []
    out = []
    for n in items:
        rel_t = n.get("relatedTickers") or []
        when = pd.Timestamp(n.get("providerPublishTime", 0), unit="s")
        title = n.get("title", "")
        named = (key and key in title.lower()) or (tick and tick.search(title)) or f"({symbol})" in title
        if symbol in rel_t and named and when >= since:
            out.append({"title": n.get("title", ""), "publisher": n.get("publisher"),
                        "link": n.get("link"), "date": when.strftime("%Y-%m-%d"),
                        "takeover": bool(TAKEOVER.search(n.get("title", "")))})
    return out[:limit]


def _expiry(x) -> pd.Timestamp | None:
    if not isinstance(x, str) or not x:
        return None
    try:
        d = pd.to_datetime(x, format="mixed")
    except (ValueError, TypeError):
        return None
    # "Feb 2016" style: no day given, so use month end to be safe.
    return d + pd.offsets.MonthEnd(0) if re.fullmatch(r"[A-Za-z]{3} \d{4}", x.strip()) else d


def _calibrated(p: float, calib: list[dict]) -> tuple[float, float]:
    """Map a model probability to the hit rate and mean excess that similarly
    scored trades actually achieved out of sample (nearest calibration bucket)."""
    b = min(calib, key=lambda c: abs(c["predicted"] - p))
    return b["realized"], b["mean_excess_6m"]


def _slug(name) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")


def build(asof: pd.Timestamp | None = None, news: bool = True) -> dict:
    data, px, spy = history()
    asof = pd.Timestamp(asof or px.index.max()).normalize()
    bt, predict = backtest(data.dropna(subset=FEATURES))
    cut, calib = bt["buy_threshold"], bt["calibration"]
    p0, k, unit_var = data.attrs["p0"], data.attrs["k"], data.attrs["unit_var"]
    since = asof - pd.Timedelta(days=RECENT_DAYS)

    all_trades = pd.read_parquet(PROCESSED / "trades.parquet")
    priced = all_trades.symbol.isin(px.columns)
    recent = all_trades[(all_trades.filing_date > since) & (all_trades.filing_date <= asof)].copy()

    # Score recent stock buys as if entering today.
    rb = recent[(recent.side == "buy") & recent.symbol.isin(px.columns)].copy()
    if len(rb):
        rb = rb.join(features(rb, px, spy, asof=asof).drop(columns=["excess_6m", "outcome_known", "ret_6m"]))
        rb["crowd"] = add_crowd(rb, all_trades[(all_trades.side == "buy") & priced])
        rb["member_odds"] = add_member_odds(rb, data[data.excess_6m.notna()], p0, k, unit_var)
        rb = rb.dropna(subset=FEATURES)
        rb["p"] = predict(rb[FEATURES])

    # Bad-case percentiles for sizing: the member's own copied buys if 30+, else everyone's.
    done = data[data.ret_6m.notna()]
    base_pct = {f"p{q}": float(np.percentile(done.ret_6m, q)) for q in odds.PERCENTILES}
    by_member = {m: {f"p{q}": float(np.percentile(g.ret_6m, q)) for q in odds.PERCENTILES}
                 for m, g in done.groupby("member") if len(g) >= 30}

    other = pd.read_parquet(PROCESSED / "other_trades.parquet")
    other = other[(other.filing_date > since) & (other.filing_date <= asof)]

    long_name = prices.load_meta().set_index("symbol").long_name
    news_cache: dict[str, list] = {}

    def get_news(sym):
        if not news or not isinstance(sym, str):
            return []
        if sym not in news_cache:
            news_cache[sym] = fetch_news(sym, asof - pd.Timedelta(days=30), long_name=long_name.get(sym))
        return news_cache[sym]

    sells_note = ("Stocks members sold went on to trail SPY by about 2.6% a year in this study, "
                  "though that gap disappears after adjusting for risk factors.")
    rows = []

    def row(r, asset_class, **extra):
        rows.append({
            "member_id": _slug(r.member), "member": r.member, "chamber": r.chamber, "party": r.party,
            "filing_date": r.filing_date.strftime("%Y-%m-%d"), "tx_date": r.tx_date.strftime("%Y-%m-%d"),
            "delay_days": int(r.delay_days), "ticker": r.ticker if isinstance(r.ticker, str) else None,
            "asset_name": str(long_name.get(getattr(r, "symbol", None)) or r.asset_name or "")[:80],
            "asset_class": asset_class, "side": r.side,
            "owner": r.owner, "amount_raw": r.amount_raw, "source_url": r.source_url, **extra,
        })

    for idx, r in recent.iterrows():
        sym = r.symbol if r.symbol in px.columns else None
        nws = get_news(sym)
        takeover = any(n["takeover"] for n in nws)
        if r.side == "sell":
            row(r, "Stock", rec="sell_if_owned", reasons=[sells_note], news=nws)
            continue
        if idx not in rb.index:
            row(r, "Stock", rec="not_rated", reasons=["No current price data for this ticker."], news=nws)
            continue
        q = rb.loc[idx]
        grp = bt["buy_group"] if q.p >= cut else bt["rest"]
        hit, exp_ex = grp["hit_rate"], grp["mean_excess_6m"]
        reasons = [
            f"Member's track record, adjusted for luck: {q.member_odds:.0%} of copied buys beat SPY.",
            f"Since they traded, the stock is {q.runup:+.1%} vs SPY (past run-ups did not hurt; momentum helped slightly).",
            f"Last 6 months: {q.momentum:+.1%} vs SPY.",
            (f"{int(q.crowd)} other member(s) disclosed buying it in the last 30 days." if q.crowd
             else "No other members disclosed buying it in the last 30 days."),
        ]
        if r.delay_days > LATE_FILING_DAYS:
            rec = "dont_buy"
            reasons.insert(0, f"Filed {int(r.delay_days)} days after the trade. Late filings trailed SPY by 4.7% over 6 months.")
        elif takeover:
            rec = "dont_buy"
            reasons.insert(0, "Recent takeover or merger headline: the price is likely pinned to the deal.")
        elif q.p >= cut:
            rec = "buy" if bt["validated"] else "watch"
        else:
            rec = "dont_buy"
        row(r, "Stock", rec=rec, confidence=round(hit, 3), expected_excess_6m=round(exp_ex, 4),
            score=round(float(q.p), 4), reasons=reasons, news=nws,
            features={f: round(float(q[f]), 4) for f in ("member_odds", "runup", "momentum", "crowd")},
            percentiles=by_member.get(r.member, base_pct))

    other = other.assign(symbol=other.ticker.map(lambda t: prices.yf_symbol(t) if isinstance(t, str) else None))
    for _, r in other.iterrows():
        cls = r.asset_class
        if r.side == "sell":
            rec = "sell_if_owned" if cls in ("Options", "Funds & ETFs") else "n/a"
            row(r, cls, rec=rec, reasons=[] if rec == "n/a" else ["A member closed or reduced this position."])
            continue
        if cls == "Options":
            exp = _expiry(r.expiry)
            sym = prices.yf_symbol(r.ticker) if isinstance(r.ticker, str) else None
            nws = get_news(sym if sym in px.columns else None)
            opt = {"type": r.option_type, "strike": None if pd.isna(r.strike) else float(r.strike), "expiry": r.expiry}
            if exp is not None and exp < asof:
                row(r, cls, rec="expired", reasons=[f"This option expired on {exp.date()}."], news=nws, option=opt)
                continue
            underlying = rb[rb.symbol == sym] if sym else rb.iloc[:0]
            extra = ([f"{r.ticker} stock itself is rated in the stock picks on this page."] if len(underlying) else [])
            row(r, cls, rec="not_rated", news=nws, option=opt,
                reasons=["Option prices are not available, so options are not rated. Sized as a total loss.", *extra])
        elif cls == "Funds & ETFs":
            row(r, cls, rec="not_rated", reasons=["The model was built and tested on individual stocks, not funds."])
        else:
            row(r, cls, rec="n/a", reasons=["Not something an ordinary investor can easily buy, or no price data."])

    order = {"buy": 0, "watch": 1, "sell_if_owned": 2, "dont_buy": 3, "not_rated": 4, "expired": 5, "n/a": 6}
    rows.sort(key=lambda x: (order[x["rec"]], -(x.get("confidence") or 0), x["filing_date"]))
    out = {
        "generated": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "asof": asof.strftime("%Y-%m-%d"), "window_days": RECENT_DAYS, "late_filing_days": LATE_FILING_DAYS,
        "model": bt, "base_percentiles": base_pct,
        "counts": {k_: sum(r["rec"] == k_ for r in rows) for k_ in order},
        "rows": rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    clean = json.loads(json.dumps(out, default=float).replace("NaN", "null"))
    (OUT / "recs.json").write_text(json.dumps(clean, separators=(",", ":")))
    return out


if __name__ == "__main__":
    import sys
    if "--backtest" not in sys.argv:
        o = build()
        print(o["asof"], "window", o["window_days"], "days |", o["counts"], "| validated:", o["model"]["validated"])
        for r in [x for x in o["rows"] if x["rec"] in ("buy", "watch")][:8]:
            print(" ", r["rec"], r["ticker"], r["member"], r["confidence"], r["expected_excess_6m"],
                  [n["title"][:50] for n in r["news"]][:1])
        raise SystemExit
    data, _, _ = history()
    bt, _ = backtest(data.dropna(subset=FEATURES))
    print(json.dumps({k: v for k, v in bt.items() if k != "calibration"}, indent=1, default=float))
    print("calibration:", [(round(c["predicted"], 3), round(c["realized"], 3)) for c in bt["calibration"]])
