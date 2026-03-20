import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Check if building for Tauri (tauri CLI sets this)
const isTauri = process.env.TAURI_ENV_PLATFORM !== undefined

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://34.22.70.164:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      // Only externalize Tauri plugins when NOT building for Tauri (e.g., Docker build)
      external: isTauri ? [] : ['@tauri-apps/plugin-shell'],
    },
  },
})
