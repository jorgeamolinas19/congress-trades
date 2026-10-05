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
  build: { chunkSizeWarningLimit: 2000 },
})
