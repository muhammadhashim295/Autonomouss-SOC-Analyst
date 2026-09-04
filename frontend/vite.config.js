import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/alerts': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/settings': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/cases': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/memory': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
