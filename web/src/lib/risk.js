// Position sizing from the viewer's own risk settings. This never says whether
// to buy. It answers: "if I copy this, what's the most I should put in so a bad
// outcome costs me no more than I said I'm willing to lose?"
import { reactive, watch } from 'vue'
import { usd as money } from './format'

const KEY = 'risk-settings'
const defaults = { portfolio: 1000, maxLossPct: 2, tolerance: 'moderate' }
let saved = {}
try { saved = JSON.parse(localStorage.getItem(KEY) || '{}') } catch (e) { saved = {} }

// One store shared by every page; remembered in this browser only.
export const risk = reactive({ ...defaults, ...saved })
watch(risk, (v) => { try { localStorage.setItem(KEY, JSON.stringify(v)) } catch (e) { /* storage blocked */ } }, { deep: true })

// Risk tolerance picks how bad a historical outcome to plan for, and caps any
// single position as a share of the portfolio.
export const TOLERANCES = {
  conservative: { label: 'Conservative', pctl: 'p1', badCase: 'worst 1-in-100', cap: 0.05 },
  moderate: { label: 'Moderate', pctl: 'p5', badCase: 'worst 1-in-20', cap: 0.1 },
  aggressive: { label: 'Aggressive', pctl: 'p10', badCase: 'worst 1-in-10', cap: 0.2 },
}

export const lossBudget = () => Math.max(0, Number(risk.portfolio) || 0) * (Number(risk.maxLossPct) || 0) / 100

/**
 * Most to put into one copied trade.
 * @param assetClass 'Stock' | 'Funds & ETFs' | 'Options' | 'Bonds & Treasuries' | 'Crypto' | 'Private & other'
 * @param side 'buy' | 'sell'
 * @param percentiles historical 6-month return percentiles for this kind of trade (stocks/ETFs)
 * @returns {{ amount: number|null, short: string, reason: string }}
 */
export function sizeTrade({ assetClass = 'Stock', side = 'buy', percentiles = null }) {
  const portfolio = Math.max(0, Number(risk.portfolio) || 0)
  const budget = lossBudget()
  const tol = TOLERANCES[risk.tolerance] || TOLERANCES.moderate
  const cap = tol.cap * portfolio

  if (side !== 'buy') return { amount: null, short: '—', reason: 'A disclosed sale: there is nothing to buy.' }
  if (assetClass === 'Private & other') {
    return { amount: null, short: 'n/a', reason: 'Private holdings and similar assets usually are not available to ordinary investors.' }
  }
  if (assetClass === 'Options' || assetClass === 'Bonds & Treasuries' || assetClass === 'Crypto') {
    const why = assetClass === 'Options'
      ? 'An option can expire worthless, so plan to lose all of it.'
      : 'There is no reliable price history for this, so it is sized as if all of it could be lost.'
    const amount = Math.min(budget, cap)
    return { amount, short: money(amount), reason: `${why} At most your loss limit of ${money(budget)}${amount < budget ? `, capped at ${Math.round(tol.cap * 100)}% of your portfolio` : ''}.` }
  }
  // Stocks and ETFs: size so the historical bad case loses at most the budget.
  const p = percentiles?.[tol.pctl]
  const badLoss = Math.max(0.05, p === undefined || p === null ? 0.5 : -p)
  const amount = Math.min(budget / badLoss, cap)
  return {
    amount, short: money(amount),
    reason: `In the ${tol.badCase} past outcomes this kind of copied trade fell ${Math.round(badLoss * 100)}% or more in 6 months. `
      + `${money(amount)} × ${Math.round(badLoss * 100)}% ≈ ${money(amount * badLoss)}, within your ${money(budget)} limit`
      + `${amount >= cap - 0.005 ? ` (capped at ${Math.round(tol.cap * 100)}% of your portfolio)` : ''}.`,
  }
}
