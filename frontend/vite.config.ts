import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Fail if 5173 is taken instead of silently moving to another port, so the
    // URL in the docs always reaches this app.
    port: 5173,
    strictPort: true,
    // Forward API calls to the FastAPI backend during development.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
