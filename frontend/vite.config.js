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
    // Binds to localhost by default (host is left unset), which matters:
    // src/api.js's backend URL has to use the same host "localhost", not
    // "127.0.0.1", or the session cookie from /login silently fails to
    // attach to later requests. See the comment there for why.
  },
})
