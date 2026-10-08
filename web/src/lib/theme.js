import { ref } from 'vue'

const current = ref(document.documentElement.getAttribute('data-theme') || 'light')

export function useTheme() {
  const toggle = () => {
    current.value = current.value === 'dark' ? 'light' : 'dark'
    document.documentElement.setAttribute('data-theme', current.value)
    try { localStorage.setItem('theme', current.value) } catch (e) {}
  }
  return { theme: current, toggle }
}

// Chart series colors, validated for color-vision deficiency in both modes:
// orange = trade-date (member's own timing), blue = filing-date (copier), gray = SPY.
export const seriesColors = (theme) =>
  theme === 'dark'
    ? { trade: '#d95926', filing: '#3987e5', spy: '#8d8c88', agents: '#2fbf8a', stats: '#3987e5' }
    : { trade: '#eb6834', filing: '#2a78d6', spy: '#8d8c88', agents: '#1baf7a', stats: '#2a78d6' }
