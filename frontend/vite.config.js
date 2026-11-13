import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Fixed port: the backend allows this exact origin for CORS.
    port: 5173,
    strictPort: true,
    // Served on localhost to match the host in src/api.js, so the session cookie is sent.
  },
})
