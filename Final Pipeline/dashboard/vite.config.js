import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base './' so the built dashboard also opens from a file path / static host.
// Data (results/*.json) is served from public/data and fetched at runtime.
export default defineConfig({
  plugins: [react()],
  base: './',
})
