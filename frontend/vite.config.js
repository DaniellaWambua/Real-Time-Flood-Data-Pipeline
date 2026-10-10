import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Pinned rather than left to Vite's "try 5173, then the next free
    // port" default: the backend's FRONTEND_ORIGINS (backend/config.py)
    // allow-lists this exact origin for CORS, so a silent port bump here
    // would break every /api/* request with a CORS error, not a 401.
    port: 5173,
    strictPort: true,
  },
})
