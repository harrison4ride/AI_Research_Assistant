import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Kept apart from vite.config.ts on purpose: its dev-server settings (port 5173, the
// /api proxy to :8000, the IPv6 port probe) must not apply to tests, which start no
// server. Every request a component makes goes to the fetch mock in src/test/.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
    unstubGlobals: true,
    // Only the app's stylesheet, which src/test/stylesheet.ts reads to check how things look.
    css: { include: [/src\/index\.css/] },
  },
})
