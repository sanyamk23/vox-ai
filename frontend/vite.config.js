import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const BACKEND = process.env.BACKEND_INTERNAL_URL || 'http://backend:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: true,
    watch: {
      usePolling: true,
    },
    proxy: {
      '/api': {
        target: BACKEND,
        changeOrigin: true,
        secure: false,
      },
      '/ws': {
        target: BACKEND.replace(/^http/, 'ws'),
        ws: true,
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
