import frappeUIPreset, { content as frappeUIContent } from 'frappe-ui/tailwind'
import typography from '@tailwindcss/typography'

export default {
  presets: [frappeUIPreset],
  content: ['./index.html', './src/**/*.{vue,js}', ...frappeUIContent],
  plugins: [typography],
}
