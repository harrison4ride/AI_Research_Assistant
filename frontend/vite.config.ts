import net from 'node:net'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

const PORT = 5173

// Vite listens on 127.0.0.1 only (see `host` below), so strictPort can't see a
// different program on [::1]:5173. Browsers try ::1 first for "localhost" and
// would show that program instead of this app, so refuse to start in that case.
function failIfTakenOnIpv6(port: number): Plugin {
  return {
    name: 'fail-if-taken-on-ipv6',
    apply: 'serve',
    configureServer() {
      return new Promise<void>((resolve, reject) => {
        const probe = net.createServer()
        probe.once('error', (err: NodeJS.ErrnoException) => {
          if (err.code === 'EADDRINUSE') {
            reject(
              new Error(
                `Port ${port} is already in use on [::1] by another program, which ` +
                  `http://localhost:${port} would reach instead of this app. ` +
                  `Find it with: lsof -i :${port}`,
              ),
            )
          } else {
            resolve() // IPv6 unavailable: nothing can shadow this server there.
          }
        })
        probe.listen({ host: '::1', port, exclusive: true }, () => probe.close(() => resolve()))
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), failIfTakenOnIpv6(PORT)],
  server: {
    // Listen on IPv4 like the backend does. Vite's default ("localhost") binds
    // only the IPv6 address ::1 on macOS, so http://127.0.0.1:5173 was refused.
    // Browsers still reach http://localhost:5173 through their IPv4 fallback.
    host: '127.0.0.1',
    // Fail if 5173 is taken instead of silently moving to another port, so the
    // URL in the docs always reaches this app.
    port: PORT,
    strictPort: true,
    // Forward API calls to the FastAPI backend during development.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  build: {
    // The PDF viewer chunk (PDF.js, ~630 kB) is loaded lazily, only on the
    // reader page, so its size does not slow down the rest of the app.
    chunkSizeWarningLimit: 700,
  },
})
