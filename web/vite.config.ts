import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      '/health': 'http://127.0.0.1:1601',
      '/ready': 'http://127.0.0.1:1601',
      '/v1': 'http://127.0.0.1:1601',
    },
  },
})
