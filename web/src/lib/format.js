export const pct = (x, digits = 1, sign = false) => {
  if (x === null || x === undefined || Number.isNaN(x)) return '—'
  const s = (x * 100).toFixed(digits)
  return `${sign && x > 0 ? '+' : ''}${s}%`
}
export const signedPct = (x, digits = 1) => pct(x, digits, true)
export const num = (x) => (x === null || x === undefined ? '—' : Number(x).toLocaleString('en-US'))
export const tstat = (t) => (t === null || t === undefined ? '—' : t.toFixed(2))
export const date = (d) =>
  d ? new Date(`${d}T00:00:00`).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }) : '—'
export const money = (x) => {
  if (!x) return '—'
  if (x >= 1e9) return `$${(x / 1e9).toFixed(1)}B`
  if (x >= 1e6) return `$${(x / 1e6).toFixed(1)}M`
  if (x >= 1e3) return `$${(x / 1e3).toFixed(0)}k`
  return `$${x.toFixed(0)}`
}
export const usd = (x) =>
  x === null || x === undefined || Number.isNaN(x)
    ? '—'
    : x.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: x < 10 ? 2 : 0 })
export const partyShort = (p) => ({ Democrat: 'D', Republican: 'R', Independent: 'I', Libertarian: 'L' })[p] || '?'
export const memberTag = (m) => [partyShort(m.party), m.state].filter(Boolean).join('-') + ` · ${m.chamber}`

// Excess return vs. SPY gets a text color, but the sign is always printed too,
// so the meaning never rests on color alone.
export const excessClass = (x) =>
  x === null || x === undefined ? 'text-ink-gray-5' : x > 0 ? 'text-ink-green-6' : x < 0 ? 'text-ink-red-6' : 'text-ink-gray-7'

export const VERDICTS = {
  beat_significant: { label: 'Beat SPY · significant', theme: 'green', variant: 'solid' },
  beat: { label: 'Beat SPY · not significant', theme: 'green', variant: 'subtle' },
  lagged: { label: 'Trailed SPY · not significant', theme: 'red', variant: 'subtle' },
  lagged_significant: { label: 'Trailed SPY · significant', theme: 'red', variant: 'solid' },
  insufficient: { label: 'Too few trades to judge', theme: 'gray', variant: 'subtle' },
}
