# Copying Congress: Is There an Investable Edge?

*Findings memo · October 2026 · data through August 2026*

## Question

Members of Congress must publicly disclose their stock trades within 45 days. A
popular idea holds that they trade on privileged information and that the public
can profit by copying them once the trades are disclosed. This memo tests that
idea with three questions:

1. Do congressional purchases beat the market from the day the member trades?
2. If so, does the edge survive the disclosure delay?
3. Is any outperformance genuine alpha, or just exposure to known risk factors
   such as tech, small caps or momentum?

## Bottom line

**No.** There is no detectable edge at the trade date, so there is nothing for
the disclosure delay to destroy, and nothing left after factor adjustment. A
copier who bought every disclosed purchase the day after filing earned 13.7% a
year from 2014 to 2026, against 14.1% for SPY. That is a factor-adjusted alpha
of +0.9% a year with a t-statistic of 1.0. The 95% confidence interval is −0.9%
to +2.7% a year, before trading costs.

## Data

I built the dataset directly from the official sources rather than relying on a
third-party feed:
- **Senate:** 1,827 electronic Periodic Transaction Reports from the Senate eFD system.
- **House:** 5,657 electronic reports, as PDFs, from the House Clerk.

After removing options, bonds and funds, consolidating amended filings, and
matching each ticker to a priced security, the sample has **43,520 stock trades
(21,561 purchases) by 289 members**. The median trade is disclosed 27 days late,
and 15% are disclosed after the 45-day deadline. One House member disclosed a
2014 trade in 2017. This is why the investable test must key off the filing
date, never the trade date.

**Validation.** I compared my Senate parse with an independent public dataset
for 2014–2020:
- 97.8% of that dataset's stock trades appear in mine.
- Most of the remaining gap comes from ETFs that the other dataset labels as stock.

A stratified 50-trade sample, linked to the original filings, is included for
manual audit. The parse also surfaced real data hazards, each handled
explicitly:
- **Recycled tickers.** An old filing's symbol now belongs to a different
  company. 355 trades were caught by a name check.
- **Renamed companies.** Square is now XYZ and Marsh McLennan is now MRSH. These
  would otherwise look like delistings.
- **Garbled PDFs.** Older House PDFs scramble letter case, so "AXP" prints as "aXP".

## Method

I built two calendar-time portfolios that hold every disclosed purchase for six
months, equally weighted:
- **Trade-date portfolio.** Buys at the close on the day the member traded. It
  measures what members earned, and no outsider could have run it.
- **Filing-date portfolio.** Buys at the close on the trading day *after* the
  disclosure, so it never uses information before it was public. It measures
  what a copier could earn.

I then ran three analyses:
- **Factor regressions.** Daily portfolio returns regressed on the market, size,
  value, profitability, investment and momentum factors (Fama-French 5 plus
  momentum), with autocorrelation-robust standard errors.
- **Event study.** Each purchase's return relative to SPY, before and after the
  trade and the filing.
- **Robustness grid.** Twenty variations of each portfolio, with a correction
  for testing many slices at once.

## Findings

**1. No edge at the trade date.**

| | Annual return | Sharpe | FF5+Mom alpha (t) |
|---|---|---|---|
| Trade-date portfolio | 13.9% | 0.70 | +1.1% (1.2) |
| Filing-date portfolio | 13.7% | 0.69 | +0.9% (1.0) |
| SPY | 14.1% | 0.74 | — |

- **Event study:** six months after a purchase, the average stock is −0.06%
  against SPY (t = −0.2).
- **No pre-trade run-up:** the 20 days before the trade show none (t = 0.5).
- **No short-horizon edge:** the 1-week, 1-month and 3-month windows are flat
  too. The largest t-statistic at any horizon is 1.04.

**2. The disclosure delay costs nothing, because there is nothing to lose.** The
return gap between buying at the trade date and buying after the filing has an
alpha of +0.15% a year (t = 0.4). Even at the edge of the confidence interval,
the delay costs under 1% a year.

**3. What return there is comes from market exposure.**
- **Market exposure.** The portfolios hold about 340 stocks, have a market beta
  of 0.98, and the factors explain 97% of their daily variance.
- **Factor tilts.** There are mild tilts toward small caps (+0.12) and value
  (+0.09) and slightly *against* momentum (−0.08). That is not the "tech and
  growth" profile the popular story assumes.
- **Concentration.** The small positive point estimate comes almost entirely
  from five mega-cap tech names (NVDA, AAPL, MSFT, AMZN, META). Together they
  supply 15% of the portfolio's return. Excluding them cuts alpha from 0.9% to
  0.1% a year, and excluding the whole technology sector cuts it to 0.1%.
- **Sales.** Stocks members *sell* go on to trail SPY by 2.6% a year, which
  looks like informed selling. But it shrinks to −0.8% (t = −0.6) once factor
  exposures are controlled for. It is a tilt, not information.

**4. Robustness.** None of the 40 slice tests is significant at the 5% level,
where about two false positives would be expected by chance. The slices are:
- House vs. Senate
- Democrats vs. Republicans
- Members' own accounts vs. spouses'
- Trades over $15k
- Dollar weighting at the low, middle or high end of the disclosed range
- Holding periods of 1, 3 or 12 months
- Selling when the member's own sale is disclosed
- Three subperiods
- Excluding top names or tech

The largest point estimates are for the Senate (+2.2%, t = 1.3) and Republicans
(+1.7%, t = 1.3). Slicing many ways and reporting the best slice is exactly
what produces headlines about congressional "outperformance". After a Holm
correction, every p-value is 1.0.

## Limitations

- **Survivorship.** 11% of cleaned trades are in companies yfinance no longer
  prices, mostly acquisition targets (Twitter, Activision, Celgene). Targets
  tend to rise on acquisition, so excluding them probably biases results slightly
  against the copier. That bias is small relative to the confidence interval.
- **Paper filings.** 26% of House and 17% of Senate reports are scanned images
  and were excluded. They are concentrated in early years and among specific
  members.
- **Amounts are ranges.** Results are similar using the low, middle or high end
  of each disclosed range.
- **No trading costs.** Daily rebalancing across about 340 names would cost
  money. Costs can only make the investable result worse.
- **Statistical power.** The test cannot rule out an alpha of 1–2% a year.
  Detecting that reliably would need decades of data. What it can rule out is an
  edge large enough to matter to an ordinary investor after costs.
- **Scope.** This is an average across all members. A handful of individual
  members could still be skilled. Identifying them without overfitting is a
  separate, harder question.
