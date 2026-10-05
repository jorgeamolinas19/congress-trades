<template>
  <article class="prose prose-gray max-w-3xl text-ink-gray-8 dark:prose-invert">
    <h1>Methodology</h1>
    <p>
      Members of Congress must report stock trades within 45 days in Periodic Transaction Reports. This site
      parses every electronically filed report since 2014: Senate reports from the Senate eFD system (HTML)
      and House reports from the House Clerk (PDF). It then measures how the disclosed purchases performed.
    </p>

    <h2>Two questions, two portfolios</h2>
    <ul>
      <li><strong>Their timing.</strong> Each purchase is bought at the close on the trade date and held six
        months. This measures what the member's picks earned, but nobody outside their household could have run it.</li>
      <li><strong>Copying them.</strong> Each purchase is bought at the close on the trading day <em>after</em> it
        was disclosed. Filings can appear after the market closes, so buying on the disclosure day itself
        would use information before it was public.</li>
    </ul>
    <p>
      Open positions are equally weighted. "vs SPY" compares the portfolio's annualized return with SPY's over
      the same days. <strong>Alpha</strong> is the return left after controlling for the market, size, value,
      profitability, investment and momentum factors (Fama-French 5 + momentum), with autocorrelation-robust
      standard errors.
    </p>

    <h2>Why "significant" is rare</h2>
    <p>
      With more than a hundred members, a few will beat the market by luck alone: at a 5% threshold, about one
      in twenty. Verdicts therefore use a Holm correction across all members with enough trades. A member
      is labeled as significantly beating the market only if their alpha survives that correction. Members
      with fewer than 10 stock purchases, or less than a year of holdings, get no verdict.
    </p>

    <h2>What's not included</h2>
    <ul>
      <li><strong>Options, bonds, funds and ETFs.</strong> Only common stock is analyzed. Some well-known traders
        (Nancy Pelosi's household, for example) trade mainly through options, so this site shows only part of
        their activity.</li>
      <li><strong>Paper filings.</strong> About 26% of House and 17% of Senate reports are scanned images, mostly from
        earlier years, and are excluded.</li>
      <li><strong>Delisted stocks.</strong> About 11% of trades are in companies that have since been acquired or
        delisted, which the free price source no longer covers.</li>
      <li><strong>Exact amounts.</strong> Trades are disclosed as ranges, such as $1,001–$15,000. Dollar figures use range midpoints.</li>
    </ul>

    <h2>Data quality</h2>
    <p>
      The Senate parse was cross-checked against an independent dataset for 2014–2020: 97.8% of its stock
      trades appear here. Each trade links to its original filing so you can verify it. Parsing errors are
      possible. If you find one, please open an issue on GitHub.
    </p>

    <p>
      Full code, tests and a two-page findings memo:
      <a href="https://github.com/jorgeamolinas19/congress-trades" target="_blank" rel="noopener">github.com/jorgeamolinas19/congress-trades</a>.
      Nothing here is investment advice.
    </p>
  </article>
</template>
