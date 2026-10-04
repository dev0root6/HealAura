import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Allow Cloudflare quick tunnels (*.trycloudflare.com) to reach the dev server.
    allowedHosts: ['.trycloudflare.com'],
    proxy: {
      '/entries': 'http://127.0.0.1:8000',
      '/events': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      '/counsellors': 'http://127.0.0.1:8000',
      // ws: true carries the real-time community socket (/community/ws).
      '/community': { target: 'http://127.0.0.1:8000', ws: true },
      '/auth': 'http://127.0.0.1:8000',
      '/friends': 'http://127.0.0.1:8000',
    },
  },
})