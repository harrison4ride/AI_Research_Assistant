// Starts the app for the Playwright tests (see playwright.config.ts):
//  1. checks that E2E_PORT is free, so the tests can never talk to another server
//     (such as a development server on :8000);
//  2. builds the UI into a new temporary folder (frontend/dist is left alone);
//  3. runs the real backend on E2E_PORT with fake outside services and a fake LLM
//     (backend/tests/support/e2e_server.py), serving that build.
// The temporary folder, which also holds the test database, is deleted on exit.
import { spawn, spawnSync } from 'node:child_process'
import { mkdtempSync, rmSync } from 'node:fs'
import net from 'node:net'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const backendDir = path.resolve(frontendDir, '../backend')
const port = Number(process.env.E2E_PORT ?? 8765)

function portIsFree(host) {
  return new Promise((resolve) => {
    const probe = net.createServer()
    probe.once('error', (err) => resolve(err.code !== 'EADDRINUSE'))
    probe.listen({ host, port, exclusive: true }, () => probe.close(() => resolve(true)))
  })
}

if (!(await portIsFree('127.0.0.1')) || !(await portIsFree('::1'))) {
  console.error(`Port ${port} is in use. Stop that program or pick another port with E2E_PORT=<port>.`)
  process.exit(1)
}

const runDir = mkdtempSync(path.join(os.tmpdir(), 'ra-e2e-'))
const removeRunDir = () => rmSync(runDir, { recursive: true, force: true })

const build = spawnSync(
  path.join(frontendDir, 'node_modules', '.bin', 'vite'),
  ['build', '--outDir', path.join(runDir, 'dist'), '--emptyOutDir', '--logLevel', 'warn'],
  { cwd: frontendDir, stdio: 'inherit' },
)
if (build.status !== 0) {
  removeRunDir()
  process.exit(build.status ?? 1)
}

const server = spawn(
  'uv',
  ['run', '--quiet', 'python', 'tests/support/e2e_server.py', '--port', String(port), '--run-dir', runDir],
  { cwd: backendDir, stdio: 'inherit' },
)
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.kill(signal))
server.on('exit', (code, signal) => {
  removeRunDir()
  process.exit(code ?? (signal ? 0 : 1))
})
