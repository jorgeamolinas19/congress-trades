import pandas as pd
import pytest

from congress import agents
from congress.agents import (BudgetExceeded, BudgetGuard, action_for, add_to_ledger, can_run, estimate_run_cost,
                             is_infrastructure_failure, is_quota_error, month_spent, new_state, price_usd,
                             register_stats_picks, select_candidates)


def test_prices_use_the_longest_matching_model_and_charge_unknowns_a_lot():
    assert price_usd("gpt-4.1-mini-2025-04-14", 1_000_000, 0) == pytest.approx(0.40)    # not gpt-4.1's $2.00
    assert price_usd("gpt-5-mini", 0, 1_000_000) == pytest.approx(2.00)
    assert price_usd("brand-new-model", 1_000_000, 0) == pytest.approx(10.0)             # unknown -> expensive


def test_guard_meters_with_a_safety_margin_and_aborts_over_the_ceiling():
    g = BudgetGuard(max_usd=0.10, fallback_model="gpt-4.1-mini")
    g.record("gpt-4.1-mini-2025-04-14", 100_000, 10_000)           # 0.04 + 0.016 = 0.056 raw
    assert g.usd == pytest.approx(0.056 * agents.SAFETY)
    with pytest.raises(BudgetExceeded):
        g.record("gpt-4.1-mini", 100_000, 10_000)                   # 0.112 raw * 1.25 > 0.10
    assert g.tokens == (200_000, 20_000)


def test_guard_charges_a_flat_amount_for_calls_that_report_no_usage():
    g = BudgetGuard(max_usd=1.0)
    g.record(None, None, None)
    assert g.untracked == 1 and g.usd == pytest.approx(agents.UNTRACKED_CALL_USD * agents.SAFETY)


def test_a_langchain_style_response_is_metered():
    class Msg:
        usage_metadata = {"input_tokens": 1000, "output_tokens": 500}
        response_metadata = {"model_name": "gpt-5-mini-2025-08-07"}

    class Gen:
        message = Msg()

    class Resp:
        generations = [[Gen()]]
        llm_output = None

    g = BudgetGuard(max_usd=1.0)
    g.on_llm_end(Resp())
    assert g.by_model["gpt-5-mini-2025-08-07"] == {"in": 1000, "out": 500, "calls": 1}
    assert g.raise_error is True        # without this langchain would swallow BudgetExceeded


def test_hard_stop_and_pacing():
    s = new_state()
    d = pd.Timestamp
    assert can_run(s, d("2026-10-01"), 0.15)[0]                      # first run of the month: allowed
    add_to_ledger(s, d("2026-10-01"), 0.15, 1, 1)
    ok, why = can_run(s, d("2026-10-01"), 0.15)
    assert not ok and "pacing" in why                                 # a second run on day 1 is ahead of pace
    assert can_run(s, d("2026-10-08"), 0.15)[0]                       # a week on, there is room again
    add_to_ledger(s, d("2026-10-20"), 4.50, 1, 1)
    ok, why = can_run(s, d("2026-10-31"), 0.40)
    assert not ok and "monthly budget" in why                         # 4.65 + 0.40 > 95% of $5


def test_the_ledger_is_per_month():
    s = new_state()
    add_to_ledger(s, pd.Timestamp("2026-10-31"), 3.0, 10, 5)
    assert month_spent(s, pd.Timestamp("2026-10-31")) == 3.0 and month_spent(s, pd.Timestamp("2026-11-01")) == 0.0


def test_run_estimate_tracks_recent_cost_but_is_capped():
    s = new_state()
    assert estimate_run_cost(s) == agents.DEFAULT_RUN_ESTIMATE
    s["decisions"] = [{"cost_usd": 0.10}, {"cost_usd": 0.30}]
    assert estimate_run_cost(s) == pytest.approx(0.36)
    s["decisions"].append({"cost_usd": 5.0})
    assert estimate_run_cost(s) == agents.MAX_RUN_USD


def test_ratings_map_to_actions():
    assert [action_for(r) for r in ("Buy", "Overweight", "Hold", "Underweight", "Sell", "REVIEW")] == \
        ["buy", "buy", "hold", "sell", "sell", "hold"]


def row(ticker, score, rec="watch", reason="", member="A B", fd="2026-10-01"):
    return {"ticker": ticker, "score": score, "rec": rec, "side": "buy", "asset_class": "Stock", "member": member,
            "member_id": "a-b", "filing_date": fd, "reasons": [reason]}


def test_candidates_skip_late_filings_takeovers_and_recently_analyzed_and_rank_by_score():
    s = new_state()
    s["decisions"] = [{"ticker": "OLD", "data_date": "2026-10-03"}]
    rows = [row("AAA", 0.50), row("BBB", 0.60), row("LATE", 0.9, "dont_buy", "Filed 90 days after the trade."),
            row("DEAL", 0.9, "dont_buy", "Recent takeover or merger headline"), row("OLD", 0.99),
            row("AAA", 0.55), {**row("SELL", 0.9), "side": "sell"}, {"ticker": "NOSCORE", "side": "buy", "asset_class": "Stock"}]
    out = select_candidates(rows, s, "2026-10-06", held=set())
    assert [r["ticker"] for r in out] == ["BBB", "AAA"] and out[1]["score"] == 0.55


def test_held_tickers_go_last():
    out = select_candidates([row("HELD", 0.9), row("NEW", 0.5)], new_state(), "2026-10-06", held={"HELD"})
    assert [r["ticker"] for r in out] == ["NEW", "HELD"]


def test_stats_picks_register_once():
    s = new_state()
    rows = [row("AAA", 0.5), row("BBB", 0.4, "dont_buy")]
    assert register_stats_picks(s, rows, "2026-10-06") == 1
    assert register_stats_picks(s, rows, "2026-10-07") == 0           # same pick on a later day isn't re-added
    assert s["stats_picks"][0]["data_date"] == "2026-10-06"


def test_quota_errors_are_recognized_and_empty_failures_are_not_decisions():
    msg = "OpenAIRateLimitError: Error code: 429 - {'error': {'code': 'credit_balance_exhausted', 'message': 'You have no credits remaining.'}}"
    assert is_quota_error(msg) and not is_quota_error("TimeoutError: slow")
    assert is_infrastructure_failure({"error": msg, "tokens_in": 0, "tokens_out": 0})
    assert not is_infrastructure_failure({"error": "run cost passed its ceiling", "tokens_in": 9000, "tokens_out": 100})
    assert not is_infrastructure_failure({"error": None, "tokens_in": 0, "tokens_out": 0})


def test_budget_abort_propagates_out_of_a_real_parallel_langgraph_run():
    """TradingAgents attaches the guard at model construction and runs its analysts
    in parallel branches; the abort must still stop the whole graph."""
    pytest.importorskip("langgraph")
    import operator
    from typing import Annotated, TypedDict

    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage
    from langgraph.graph import END, START, StateGraph

    def replies():
        while True:
            yield AIMessage(content="ok", response_metadata={"model_name": "gpt-4.1-mini"},
                            usage_metadata={"input_tokens": 60_000, "output_tokens": 5_000, "total_tokens": 65_000})

    guard = BudgetGuard(max_usd=0.05)                 # one call costs ~$0.04 padded, two exceed it
    llm = GenericFakeChatModel(messages=replies(), callbacks=[guard])

    class S(TypedDict):
        out: Annotated[list, operator.add]

    def node(state):
        return {"out": [llm.invoke("hi").content]}

    g = StateGraph(S)
    for n in "abc":
        g.add_node(n, node)
    g.add_edge(START, "a"); g.add_edge(START, "b"); g.add_edge("a", "c"); g.add_edge("b", "c"); g.add_edge("c", END)
    with pytest.raises(BudgetExceeded):
        g.compile().invoke({"out": []})
    assert guard.usd > 0.05 and guard.tokens[0] >= 120_000

    # And under the ceiling the same graph completes and is metered.
    ok = BudgetGuard(max_usd=10.0)
    llm.callbacks = [ok]
    assert g.compile().invoke({"out": []})["out"] == ["ok", "ok", "ok"]
    assert ok.by_model["gpt-4.1-mini"]["calls"] == 3
