"""Headline charts for the README and memo (static PNGs, light surface).

Colour carries identity only: blue = investable (filing-date) portfolio,
orange = theoretical (trade-date) portfolio, neutral grey = SPY benchmark.
Palette validated for colour-vision deficiency (worst adjacent CVD dE 24.7).
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .config import FIGURES, REPORTS

RES = REPORTS / "results"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
FILING, TRADE, BENCH = "#2a78d6", "#eb6834", "#8d8c88"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "legend.frameon": False, "lines.linewidth": 2, "lines.solid_capstyle": "round",
})


def _end_label(ax, x, y, text, color):
    ax.annotate(text, (x, y), xytext=(6, 0), textcoords="offset points", va="center",
                color=INK, fontsize=9, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", fc=SURFACE, ec=color, lw=1.2))


def cumulative_returns():
    d = pd.read_csv(RES / "daily_returns.csv", index_col=0, parse_dates=True)
    fig, ax = plt.subplots(figsize=(9, 4.8))
    series = [("trade_date", "Trade date (theoretical)", TRADE),
              ("filing_date", "Filing date (investable)", FILING), ("spy", "SPY", BENCH)]
    for col, label, color in series:
        g = (1 + d[col].fillna(0)).cumprod()
        # The three lines finish within a few percent of each other, so the
        # final multiple goes in the legend rather than colliding end labels.
        ax.plot(g.index, g, color=color, label=f"{label}: {g.iloc[-1]:.2f}x", lw=2 if col != "spy" else 1.6)
    ax.set_title("Growth of $1: copying congressional purchases vs. SPY")
    ax.set_ylabel("Growth of $1")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(FIGURES / "cumulative_returns.png", dpi=160)
    plt.close(fig)


def event_study():
    t = pd.read_csv(RES / "event_car_trade_date.csv", index_col=0)
    f = pd.read_csv(RES / "event_car_filing_date.csv", index_col=0)
    t = t.loc[0:126, "mean_car"]
    f = f.loc[1:127, "mean_car"]
    f.index = f.index - 1  # both curves start at their own entry close
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.axhline(0, color=INK2, lw=1)
    ax.plot(t.index, t * 100, color=TRADE, label="Buying at the member's trade date")
    ax.plot(f.index, f * 100, color=FILING, label="Buying the day after the filing")
    _end_label(ax, t.index[-1], t.iloc[-1] * 100, f"{t.iloc[-1]*100:+.2f}%", TRADE)
    _end_label(ax, f.index[-1], f.iloc[-1] * 100, f"{f.iloc[-1]*100:+.2f}%", FILING)
    ax.set_title("Average return vs. SPY after a congressional purchase")
    ax.set_xlabel("Trading days after entry")
    ax.text(0.99, 0.02, "No horizon differs from zero (month-clustered |t| <= 1.04)", transform=ax.transAxes,
            ha="right", va="bottom", color=INK2, fontsize=9)
    ax.set_ylabel("Cumulative abnormal return (%)")
    ax.legend(loc="upper left")
    ax.margins(x=0.1)
    fig.tight_layout()
    lo, hi = ax.get_ylim()
    ax.set_ylim(lo, hi + 0.45 * (hi - lo))  # headroom so the legend clears the lines
    fig.savefig(FIGURES / "event_study.png", dpi=160)
    plt.close(fig)


def factor_loadings():
    r = pd.read_csv(RES / "factor_regressions.csv")
    r = r[(r.model == "FF5+Mom") & r.portfolio.isin(["trade_date", "filing_date"])].set_index("portfolio")
    facs = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]
    names = ["Market", "Size\n(small)", "Value", "Profitability", "Investment\n(conservative)", "Momentum"]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    x = range(len(facs))
    w = 0.38
    for i, (p, color, label) in enumerate([("trade_date", TRADE, "Trade date"), ("filing_date", FILING, "Filing date")]):
        vals = [r.loc[p, f"b_{f}"] for f in facs]
        ax.bar([xi + (i - 0.5) * (w + 0.02) for xi in x], vals, width=w, color=color, label=label)
    ax.axhline(0, color=INK2, lw=1)
    ax.set_xticks(list(x), names)
    ax.set_title("What the portfolios are exposed to (FF5 + momentum betas)")
    ax.set_ylabel("Factor loading")
    ax.legend(loc="upper right")
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    fig.savefig(FIGURES / "factor_loadings.png", dpi=160)
    plt.close(fig)


def robustness_forest():
    r = pd.read_csv(RES / "robustness.csv")
    hl = pd.read_csv(RES / "factor_regressions.csv").query("model == 'FF5+Mom'")
    hl = hl[hl.portfolio.isin(["trade_date", "filing_date"])].assign(slice="Headline (all trades)")
    r = pd.concat([hl[["slice", "portfolio", "alpha_ann", "alpha_t"]], r[["slice", "portfolio", "alpha_ann", "alpha_t"]]])
    order = list(dict.fromkeys(r.slice))
    fig, ax = plt.subplots(figsize=(9, 0.36 * len(order) + 1.4))
    for i, (p, color, label, dy) in enumerate([("trade_date", TRADE, "Trade date", -0.17),
                                               ("filing_date", FILING, "Filing date", 0.17)]):
        g = r[r.portfolio == p].set_index("slice").reindex(order)
        se = (g.alpha_ann / g.alpha_t).abs()
        y = [len(order) - 1 - k + dy for k in range(len(order))]
        ax.errorbar(g.alpha_ann * 100, y, xerr=1.96 * se * 100, fmt="o", ms=5, color=color,
                    ecolor=color, elinewidth=1.5, capsize=0, label=label)
    ax.axvline(0, color=INK2, lw=1)
    ax.set_yticks(range(len(order)), order[::-1])
    ax.set_xlabel("Annualised FF5+momentum alpha (%), with 95% CI")
    ax.set_title("Alpha across robustness slices")
    ax.legend(loc="lower right")
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(FIGURES / "robustness_alpha.png", dpi=160)
    plt.close(fig)


def top_contributors(n: int = 10):
    c = pd.read_csv(RES / "contribution_filing_date.csv", index_col=0).contribution
    share = (c / c.sum()).head(n)[::-1]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    ax.barh(share.index, share * 100, color=FILING, height=0.6)
    for y, v in enumerate(share * 100):
        ax.annotate(f"{v:.1f}%", (v, y), xytext=(4, 0), textcoords="offset points", va="center", color=INK2, fontsize=9)
    ax.set_title(f"Top {n} names' share of the investable portfolio's total return")
    ax.set_xlabel("Share of summed daily return contribution (%)")
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(FIGURES / "top_contributors.png", dpi=160)
    plt.close(fig)


def all_figures():
    cumulative_returns()
    event_study()
    factor_loadings()
    robustness_forest()
    top_contributors()


if __name__ == "__main__":
    all_figures()
