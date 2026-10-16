import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'
import path from 'node:path'
import { defineConfig } from 'vite'

// frappe-ui's Vite plugin, minus the parts that assume a Frappe server behind
// the app (dev proxy, Jinja boot data, bench build paths): this is a static site.
export default defineConfig({
  plugins: [
    frappeui({ frappeProxy: false, jinjaBootData: false, buildConfig: false, codeLanguages: true }),
    vue(),
  ],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
  // esbuild (Vite's dep pre-bundler) only tries the first candidate in frappe-ui's
  // "#utils/*" imports array, which has no extension, so dev-mode pre-bundling fails
  // to resolve it. Rollup walks the whole array, so `npm run build` is unaffected.
  optimizeDeps: { exclude: ['frappe-ui'] },
  build: { chunkSizeWarningLimit: 2000 },
})
