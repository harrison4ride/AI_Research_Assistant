import { defineConfig, devices } from '@playwright/test'

// End-to-end tests: a real browser against the real app (built UI + FastAPI + SQLite),
// with fake paper-search APIs and a fake `claude` CLI, so no LLM is ever called.
// e2e/support/serve.mjs starts it on its own port with a throwaway database.
const port = Number(process.env.E2E_PORT ?? 8765)

export default defineConfig({
  testDir: './e2e',
  // One app and one database for all tests.
  workers: 1,
  fullyParallel: false,
  forbidOnly: true,
  reporter: [['list']],
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'node e2e/support/serve.mjs',
    url: `http://127.0.0.1:${port}/api/health`,
    // Never test against a server that is already running (it may hold real data).
    reuseExistingServer: false,
    timeout: 180_000,
    gracefulShutdown: { signal: 'SIGTERM', timeout: 15_000 },
    env: { E2E_PORT: String(port) },
  },
})
