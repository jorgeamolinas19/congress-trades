"""The agent desk: TradingAgents' view of new congressional buys, tracked in a
$1,000 paper account next to SPY and the statistical picks model.

    python -m congress.agents analyze AAPL     # one real (paid) analysis, recorded
    python -m congress.agents status           # budget, decisions, accounts

How it fits together
  * `run_daily` (called by congress.daily) scores the day's new disclosed buys,
    picks the best candidates that the budget allows, runs TradingAgents on each,
    and records the five-tier rating (Buy / Overweight / Hold / Underweight /
    Sell) with the debate and risk write-ups.
  * A rating becomes a paper trade by the rules in congress.paper: Buy and
    Overweight invest $100 at the next close, Sell and Underweight close the
    position, Hold does nothing; positions are closed after 20 trading days.
  * The account is replayed from the decision list every time (never stored).
  * The result goes to web/public/picks/agents.json, which is git-ignored and
    served only behind the site's password.

Money
  Every LLM call is metered by `BudgetGuard` (tokens x list price x a 25%
  safety margin). A run aborts the moment it would cross its per-run ceiling,
  and no run starts unless the month's cap (default $5) still has room after the
  run's expected cost, paced evenly across the month.
"""
from __future__ import annotations

import calendar
import copy
import json
import math
import os
import re
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import paper, prices
from .config import PROCESSED, ROOT

PRIVATE = ROOT / "data" / "private"
STATE_PATH = Path(os.environ.get("AGENTS_STATE_PATH") or PRIVATE / "agents_state.json")
OUT = Path(os.environ.get("AGENTS_OUT_PATH") or ROOT / "web" / "public" / "picks" / "agents.json")
RULES = paper.Rules()

# ---- money ---------------------------------------------------------------------
MONTHLY_CAP_USD = min(5.0, float(os.environ.get("AGENTS_MONTHLY_CAP_USD", "5.0")))
HARD_STOP = 0.95          # never plan to spend past 95% of the cap
SAFETY = 1.25             # list prices can drift; pad every estimate
MAX_RUN_USD = 0.60        # a single analysis is aborted past this
DEFAULT_RUN_ESTIMATE = 0.35
MAX_RUNS_PER_DAY = 3
UNTRACKED_CALL_USD = 0.01  # an LLM call that reports no token usage is charged this flat amount
# USD per 1M tokens (input, output). Models not listed are billed at the
# expensive UNKNOWN_PRICE so a surprise model can only overstate spend.
PRICES = {
    "gpt-5-nano": (0.05, 0.40), "gpt-5-mini": (0.25, 2.00), "gpt-5": (1.25, 10.00),
    "gpt-4.1-nano": (0.10, 0.40), "gpt-4.1-mini": (0.40, 1.60), "gpt-4.1": (2.00, 8.00),
    "gpt-4o-mini": (0.15, 0.60), "gpt-4o": (2.50, 10.00),
}
UNKNOWN_PRICE = (10.0, 40.0)

MODELS = {"quick": os.environ.get("AGENTS_QUICK_MODEL", "gpt-4.1-mini"),
          "deep": os.environ.get("AGENTS_DEEP_MODEL", "gpt-5-mini")}
# Settings that bound how much each analysis reads and says.
TA_LIMITS = {"max_debate_rounds": 1, "max_risk_discuss_rounds": 1, "max_tool_rounds": 8,
             "news_article_limit": 10, "global_news_article_limit": 5, "global_news_lookback_days": 5,
             "openai_reasoning_effort": "low", "checkpoint_enabled": False}

QUOTA_MARKERS = ("insufficient_quota", "credit_balance_exhausted", "no credits remaining", "billing_hard_limit")
MAX_CONSECUTIVE_FAILURES = 2
COOLDOWN_DAYS = 10         # don't re-analyze a ticker sooner than this
CLIP = 5000                # characters kept per report section


def price_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    key = max((k for k in PRICES if (model or "").startswith(k)), key=len, default=None)
    pin, pout = PRICES[key] if key else UNKNOWN_PRICE
    return (tokens_in * pin + tokens_out * pout) / 1e6


class BudgetExceeded(RuntimeError):
    pass


try:  # langchain is only needed when a real analysis runs
    from langchain_core.callbacks import BaseCallbackHandler as _Base
except ImportError:  # pragma: no cover
    _Base = object


class BudgetGuard(_Base):
    """Meters every LLM call; aborts the run when its estimated cost passes `max_usd`."""

    raise_error = True   # let BudgetExceeded stop the graph instead of being logged and swallowed

    def __init__(self, max_usd: float, fallback_model: str = ""):
        self.max_usd = max_usd
        self.fallback_model = fallback_model
        self.by_model: dict[str, dict] = {}
        self.untracked = 0
        self._lock = threading.Lock()

    @property
    def usd(self) -> float:
        raw = sum(price_usd(m, v["in"], v["out"]) for m, v in self.by_model.items())
        return (raw + self.untracked * UNTRACKED_CALL_USD) * SAFETY

    @property
    def tokens(self) -> tuple[int, int]:
        return (sum(v["in"] for v in self.by_model.values()), sum(v["out"] for v in self.by_model.values()))

    def record(self, model: str | None, tokens_in: int | None, tokens_out: int | None) -> None:
        with self._lock:
            if tokens_in is None and tokens_out is None:
                self.untracked += 1
            else:
                m = self.by_model.setdefault(model or self.fallback_model or "unknown", {"in": 0, "out": 0, "calls": 0})
                m["in"] += int(tokens_in or 0)
                m["out"] += int(tokens_out or 0)
                m["calls"] += 1
            over = self.usd > self.max_usd
        if over:
            raise BudgetExceeded(f"run cost passed its ${self.max_usd:.2f} ceiling (about ${self.usd:.2f})")

    def on_llm_end(self, response, **kwargs):  # langchain callback
        for gens in getattr(response, "generations", []) or []:
            for g in gens:
                msg = getattr(g, "message", None)
                um = getattr(msg, "usage_metadata", None) or {}
                meta = getattr(msg, "response_metadata", None) or {}
                model = meta.get("model_name") or meta.get("model") or (getattr(response, "llm_output", None) or {}).get("model_name")
                if um:
                    self.record(model, um.get("input_tokens"), um.get("output_tokens"))
                else:
                    self.record(model, None, None)


# ---- state -----------------------------------------------------------------------
def new_state() -> dict:
    return {"version": 1, "created": pd.Timestamp.now().strftime("%Y-%m-%d"), "decisions": [],
            "stats_picks": [], "ledger": {}, "errors": []}


def load_state(path: Path = STATE_PATH) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return new_state()


def save_state(state: dict, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, separators=(",", ":"), default=float), encoding="utf-8")
    tmp.replace(path)   # atomic: a crash can't leave half a file


def month_key(now: pd.Timestamp) -> str:
    return pd.Timestamp(now).strftime("%Y-%m")


def month_spent(state: dict, now: pd.Timestamp) -> float:
    return float(state["ledger"].get(month_key(now), {}).get("usd", 0.0))


def estimate_run_cost(state: dict) -> float:
    recent = [d["cost_usd"] for d in state["decisions"][-6:] if d.get("cost_usd")]
    return min(MAX_RUN_USD, max(recent) * 1.2) if recent else DEFAULT_RUN_ESTIMATE


def can_run(state: dict, now: pd.Timestamp, est: float, cap: float = MONTHLY_CAP_USD) -> tuple[bool, str]:
    """Whether another analysis fits: inside the hard stop, and not ahead of an
    even spend across the month (one run is always allowed if the budget has room)."""
    spent = month_spent(state, now)
    if spent + est > cap * HARD_STOP:
        return False, f"monthly budget: ${spent:.2f} spent of ${cap:.2f}, next run needs about ${est:.2f}"
    days = calendar.monthrange(now.year, now.month)[1]
    pace = cap * HARD_STOP * pd.Timestamp(now).day / days
    if spent + est > max(pace, est):
        return False, f"pacing: ${spent:.2f} spent, ${pace:.2f} allowed by day {pd.Timestamp(now).day} of {days}"
    return True, ""


def add_to_ledger(state: dict, now: pd.Timestamp, usd: float, tokens_in: int, tokens_out: int, runs: int = 1) -> None:
    m = state["ledger"].setdefault(month_key(now), {"usd": 0.0, "runs": 0, "tokens_in": 0, "tokens_out": 0})
    m["usd"] = round(m["usd"] + usd, 6)
    m["runs"] += runs
    m["tokens_in"] += int(tokens_in)
    m["tokens_out"] += int(tokens_out)


# ---- choosing what to analyze ------------------------------------------------------
def _slug(name) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")


def register_stats_picks(state: dict, rows: list[dict], data_date) -> int:
    """Remember the first day each statistical-model pick (Buy/Watch) appeared,
    so that account can be replayed later from what was known on that day."""
    have = {p["id"] for p in state["stats_picks"]}
    added = 0
    for r in rows:
        if r.get("side") == "buy" and r.get("asset_class") == "Stock" and r.get("rec") in ("buy", "watch") and r.get("ticker"):
            pid = f"{r['ticker']}|{r['member_id']}|{r['filing_date']}"
            if pid not in have:
                state["stats_picks"].append({"id": pid, "ticker": r["ticker"], "symbol": prices.yf_symbol(r["ticker"]),
                                             "member": r["member"], "data_date": pd.Timestamp(data_date).strftime("%Y-%m-%d"),
                                             "score": r.get("score") or 0.0, "action": "buy"})
                have.add(pid)
                added += 1
    return added


def select_candidates(rows: list[dict], state: dict, data_date, held: set[str], limit: int = MAX_RUNS_PER_DAY) -> list[dict]:
    """New disclosed stock buys, best statistical score first, one per ticker.
    Late filings and takeover headlines are skipped: the stats model already
    rules them out and they aren't worth the budget."""
    cutoff = pd.Timestamp(data_date) - pd.Timedelta(days=COOLDOWN_DAYS)
    recent = {d["ticker"] for d in state["decisions"] if pd.Timestamp(d["data_date"]) > cutoff}
    best: dict[str, dict] = {}
    for r in rows:
        if r.get("side") != "buy" or r.get("asset_class") != "Stock" or not r.get("ticker") or r.get("score") is None:
            continue
        first = (r.get("reasons") or [""])[0]
        if first.startswith("Filed ") or first.startswith("Recent takeover"):
            continue
        if r["ticker"] in recent:
            continue
        if r["ticker"] not in best or r["score"] > best[r["ticker"]]["score"]:
            best[r["ticker"]] = r
    ranked = sorted(best.values(), key=lambda r: (prices.yf_symbol(r["ticker"]) in held, -r["score"]))
    return ranked[:limit]


# ---- running TradingAgents ---------------------------------------------------------
def _clip(text, n: int = CLIP) -> str:
    s = (text or "").strip() if isinstance(text, str) else ""
    return s if len(s) <= n else s[:n].rstrip() + "\n…[trimmed]"


def _sections(fs: dict) -> dict:
    ids = fs.get("investment_debate_state") or {}
    rds = fs.get("risk_debate_state") or {}
    out = {
        "market": fs.get("market_report"), "sentiment": fs.get("sentiment_report"), "news": fs.get("news_report"),
        "fundamentals": fs.get("fundamentals_report"), "bull": ids.get("bull_history"), "bear": ids.get("bear_history"),
        "research_plan": fs.get("investment_plan"), "trader": fs.get("trader_investment_plan"),
        "risk_aggressive": rds.get("aggressive_history"), "risk_conservative": rds.get("conservative_history"),
        "risk_neutral": rds.get("neutral_history"), "final": fs.get("final_trade_decision"),
    }
    return {k: _clip(v) for k, v in out.items() if v}


def is_quota_error(err: str | None) -> bool:
    return bool(err) and any(m in err.lower() for m in QUOTA_MARKERS)


def is_infrastructure_failure(dec: dict) -> bool:
    """A run that failed before any model call completed told us nothing about
    the stock, so it is logged as an error rather than recorded as a decision."""
    return bool(dec.get("error")) and dec.get("tokens_in", 0) == 0 and dec.get("tokens_out", 0) == 0


def action_for(rating: str) -> str:
    return {"Buy": "buy", "Overweight": "buy", "Sell": "sell", "Underweight": "sell"}.get(rating, "hold")


def portfolio_context(account: dict | None):
    from tradingagents.portfolio import PortfolioContext, Position
    if not account:
        return PortfolioContext(cash=RULES.start_cash, currency="USD", positions=[])
    return PortfolioContext(cash=round(account["cash"], 2), currency="USD",
                            positions=[Position(ticker=p["ticker"], quantity=round(p["shares"], 4),
                                                average_price=round(p["entry_price"], 2)) for p in account["positions"]])


def analyze(row: dict, data_date, account: dict | None, max_usd: float = MAX_RUN_USD) -> dict:
    """One paid TradingAgents analysis. Always returns a decision record, even
    when the run fails or is stopped by the budget guard (then `error` is set)."""
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    ticker = row["ticker"]
    symbol = prices.yf_symbol(ticker)
    date = pd.Timestamp(data_date).strftime("%Y-%m-%d")
    work = Path(tempfile.mkdtemp(prefix="ta_"))
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg.update(TA_LIMITS)
    cfg.update({"llm_provider": "openai", "deep_think_llm": MODELS["deep"], "quick_think_llm": MODELS["quick"],
                "holding_period_days": RULES.hold_days, "benchmark_ticker": "SPY",
                # Each analysis stands alone: no carried-over memory log (its reflection calls cost tokens).
                "results_dir": str(work / "logs"), "data_cache_dir": str(work / "cache"),
                "memory_log_path": str(work / "memory" / "trading_memory.md")})
    guard = BudgetGuard(max_usd, fallback_model=MODELS["deep"])
    t0, err, fs, rating = time.time(), None, {}, "REVIEW"
    try:
        ta = TradingAgentsGraph(debug=False, config=cfg, callbacks=[guard])
        fs, rating = ta.propagate(symbol, date, portfolio=portfolio_context(account))
    except BudgetExceeded as e:
        err = str(e)
    except Exception as e:  # noqa: BLE001 - one bad ticker must not stop the day's job
        err = f"{type(e).__name__}: {e}"[:300]
    tin, tout = guard.tokens
    return {
        "id": f"{ticker}:{date}", "ticker": ticker, "symbol": symbol, "name": row.get("asset_name"),
        "member": row.get("member"), "member_id": row.get("member_id") or _slug(row.get("member")),
        "chamber": row.get("chamber"), "party": row.get("party"), "filing_date": row.get("filing_date"),
        "tx_date": row.get("tx_date"), "amount_raw": row.get("amount_raw"), "source_url": row.get("source_url"),
        "data_date": date, "run_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "rating": rating if not err else "REVIEW", "action": action_for(rating) if not err else "hold", "error": err,
        "stats_rec": row.get("rec"), "stats_score": row.get("score"), "stats_confidence": row.get("confidence"),
        "cost_usd": round(guard.usd, 4), "tokens_in": tin, "tokens_out": tout, "seconds": round(time.time() - t0),
        "models": dict(MODELS), "model_usage": {m: v for m, v in guard.by_model.items()},
        "sections": _sections(fs) if fs else {},
    }


# ---- accounts and export -------------------------------------------------------------
def load_closes() -> pd.DataFrame:
    return pd.read_parquet(prices.PRICES_PATH).sort_index()


def _agent_decisions(state: dict) -> list[dict]:
    out = []
    for i, d in enumerate(state["decisions"]):
        if d["action"] in ("buy", "sell"):
            out.append({"id": d["id"], "symbol": d["symbol"], "ticker": d["ticker"], "action": d["action"],
                        "data_date": d["data_date"], "priority": -i})
    return out


def simulate_accounts(state: dict, closes: pd.DataFrame) -> dict:
    agent_d, stats_d = _agent_decisions(state), state["stats_picks"]
    dates = [d["data_date"] for d in agent_d + stats_d]
    start = min(dates) if dates else None
    a = paper.simulate(agent_d, closes, RULES, start)
    s = paper.simulate([{**p, "priority": p.get("score", 0)} for p in stats_d], closes, RULES, start)
    spy = paper.benchmark_curve(closes, "SPY", start, RULES.start_cash) if start else []
    return {"agents": a, "stats": s, "spy": spy, "start": start}


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not math.isfinite(float(o)) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    return o


def export(state: dict, closes: pd.DataFrame, now: pd.Timestamp, note: str = "") -> dict:
    acc = simulate_accounts(state, closes)
    est = estimate_run_cost(state)
    ok, why = can_run(state, now, est)
    spent = month_spent(state, now)
    led = state["ledger"].get(month_key(now), {"runs": 0, "tokens_in": 0, "tokens_out": 0})
    outcomes = {**acc["agents"]["outcomes"]}
    decisions = []
    for d in reversed(state["decisions"]):
        if d.get("error"):
            o = {"status": "none", "note": "Run stopped before finishing: no trade."}
        else:
            o = outcomes.get(d["id"]) or {"status": "none", "note": "Hold: no trade." if d["action"] == "hold" else "No trade."}
        decisions.append({**d, "outcome": o})
    eq = {e["date"]: e["value"] for e in acc["agents"]["equity"]}
    st = {e["date"]: e["value"] for e in acc["stats"]["equity"]}
    sp = {e["date"]: e["value"] for e in acc["spy"]}
    days = sorted(set(eq) | set(st) | set(sp))
    series = [{"date": d, "agents": eq.get(d), "stats": st.get(d), "spy": sp.get(d)} for d in days]
    spy_last = acc["spy"][-1]["value"] if acc["spy"] else RULES.start_cash
    out = {
        "generated": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "data_date": pd.Timestamp(closes.index.max()).strftime("%Y-%m-%d"), "start": acc["start"],
        "rules": {"start_cash": RULES.start_cash, "position_usd": RULES.position_usd, "max_positions": RULES.max_positions,
                  "hold_days": RULES.hold_days, "slippage": RULES.slippage},
        "models": dict(MODELS), "note": note,
        "budget": {"cap": MONTHLY_CAP_USD, "month": month_key(now), "spent": round(spent, 4), "runs": led.get("runs", 0),
                   "tokens_in": led.get("tokens_in", 0), "tokens_out": led.get("tokens_out", 0),
                   "est_run": round(est, 4), "can_run": ok, "paused_because": "" if ok else why},
        "accounts": {"agents": {**paper.summarize(acc["agents"], RULES.start_cash), "positions": acc["agents"]["positions"],
                                "closed": acc["agents"]["closed"]},
                     "stats": {**paper.summarize(acc["stats"], RULES.start_cash), "positions": acc["stats"]["positions"],
                               "closed": acc["stats"]["closed"]},
                     "spy": {"value": spy_last, "return": spy_last / RULES.start_cash - 1}},
        "series": series, "decisions": decisions,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(_clean(out), separators=(",", ":")), encoding="utf-8")
    return out


# ---- the daily entry point --------------------------------------------------------------
def run_daily(picks: dict | None, closes: pd.DataFrame | None = None, now: pd.Timestamp | None = None,
              max_runtime_s: int = 2400) -> dict:
    """Register today's stats picks, run the analyses the budget allows, update
    both paper accounts and write the private export. Safe to run with no API
    key or no TradingAgents install: it then only updates the accounts."""
    now = pd.Timestamp(now or pd.Timestamp.now())
    closes = load_closes() if closes is None else closes
    data_date = closes.index.max()
    rows = (picks or {}).get("rows", [])
    state = load_state()
    new_picks = register_stats_picks(state, rows, data_date)
    ran, note = [], ""
    if not os.environ.get("OPENAI_API_KEY"):
        note = "No OPENAI_API_KEY is set, so no new analyses ran. The accounts were still updated."
    else:
        try:
            import tradingagents  # noqa: F401
        except ImportError:
            note = "TradingAgents is not installed, so no new analyses ran."
    if not note and rows:
        started = time.time()
        acc = simulate_accounts(state, closes)
        held = {p["symbol"] for p in acc["agents"]["positions"]}
        failures = 0
        for row in select_candidates(rows, state, data_date, held):
            est = estimate_run_cost(state)
            ok, why = can_run(state, now, est)
            if not ok or len(ran) >= MAX_RUNS_PER_DAY:
                note = note or f"Paused: {why}" if not ok else note
                break
            if time.time() - started > max_runtime_s:
                note = "Stopped early: the daily time limit was reached."
                break
            remaining = MONTHLY_CAP_USD * HARD_STOP - month_spent(state, now)
            dec = analyze(row, data_date, acc["agents"], max_usd=min(MAX_RUN_USD, remaining))
            if dec["error"]:
                state["errors"] = (state["errors"] + [{"at": dec["run_at"], "ticker": dec["ticker"], "error": dec["error"]}])[-50:]
            if is_infrastructure_failure(dec):
                failures += 1
                if is_quota_error(dec["error"]):
                    note = "OpenAI says the account has no credits left, so no analyses ran. Add credits and the next run resumes."
                    break
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    note = f"Stopped after {failures} failed runs in a row: {dec['error']}"
                    break
                continue
            failures = 0
            if not any(x["id"] == dec["id"] for x in state["decisions"]):
                state["decisions"].append(dec)
            add_to_ledger(state, now, dec["cost_usd"], dec["tokens_in"], dec["tokens_out"])
            ran.append(dec)
            save_state(state)                      # crash-safe: spend is recorded as soon as it happens
            acc = simulate_accounts(state, closes)  # next run sees any new position
    save_state(state)
    out = export(state, closes, now, note)
    return {"ran": [(d["ticker"], d["rating"], d["cost_usd"]) for d in ran], "new_stats_picks": new_picks,
            "budget": out["budget"], "note": note}


# ---- command line --------------------------------------------------------------------------
def _latest_rows() -> list[dict]:
    for p in (PRIVATE / "recs.json", ROOT / "web" / "public" / "picks" / "recs.json"):
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8")).get("rows", [])
    return []


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else "status"
    now = pd.Timestamp.now()
    if cmd == "analyze" and len(argv) >= 2:
        ticker = argv[1].upper()
        max_usd = float(argv[argv.index("--max-usd") + 1]) if "--max-usd" in argv else MAX_RUN_USD
        sym = prices.yf_symbol(ticker)
        print(f"refreshing prices for {sym} and SPY ...", flush=True)
        prices.refresh([sym, "SPY"])
        closes = load_closes()
        data_date = closes.index.max()
        rows = [r for r in _latest_rows() if r.get("ticker") == ticker and r.get("side") == "buy"]
        row = max(rows, key=lambda r: r.get("score") or 0) if rows else {"ticker": ticker, "member": "manual run"}
        state = load_state()
        ok, why = can_run(state, now, min(max_usd, estimate_run_cost(state)))
        if not ok:
            raise SystemExit(f"Refusing to run: {why}")
        acc = simulate_accounts(state, closes)
        print(f"analyzing {ticker} as of {data_date.date()} with {MODELS} (ceiling ${max_usd:.2f}) ...", flush=True)
        dec = analyze(row, data_date, acc["agents"], max_usd=max_usd)
        if is_infrastructure_failure(dec):
            raise SystemExit(f"The run failed before any model call completed (nothing spent, nothing recorded): {dec['error']}")
        if not any(x["id"] == dec["id"] for x in state["decisions"]):
            state["decisions"].append(dec)
        add_to_ledger(state, now, dec["cost_usd"], dec["tokens_in"], dec["tokens_out"])
        save_state(state)
        export(state, closes, now)
        print(json.dumps({k: dec[k] for k in ("ticker", "data_date", "rating", "action", "error", "cost_usd", "tokens_in",
                                              "tokens_out", "seconds", "model_usage")}, indent=1, default=float))
        print("sections:", {k: len(v) for k, v in dec["sections"].items()})
    else:
        state = load_state()
        closes = load_closes()
        out = export(state, closes, now)
        print(json.dumps({"budget": out["budget"], "accounts": {k: {kk: vv for kk, vv in v.items() if not isinstance(vv, list)}
                                                                 for k, v in out["accounts"].items()},
                          "decisions": [(d["ticker"], d["data_date"], d["rating"], d["outcome"]["status"]) for d in out["decisions"]]},
                         indent=1, default=float))


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
