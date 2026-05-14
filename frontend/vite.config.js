import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { env } from 'node:process'

const backendTarget = env.BACKEND_URL || 'http://localhost:3101'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': backendTarget,
      '/static/cards': backendTarget,
      '/static/hepan': backendTarget,
      '/static/media-cache': backendTarget,
      '/static/avatars': backendTarget,
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
