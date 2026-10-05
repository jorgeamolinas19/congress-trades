import frappeUIPreset, { content as frappeUIContent } from 'frappe-ui/tailwind'
import typography from '@tailwindcss/typography'

export default {
  presets: [frappeUIPreset],
  content: ['./index.html', './src/**/*.{vue,js}', ...frappeUIContent],
  plugins: [typography],
  theme: { extend: { fontFamily: { mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'] } } },
}
