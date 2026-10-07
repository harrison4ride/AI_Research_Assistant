import { useEffect, useState } from 'react'
import { getHealth } from './api'
import { useRoute } from './router'
import SearchPage from './pages/SearchPage'
import LibraryPage from './pages/LibraryPage'
import PaperPage from './pages/PaperPage'

export default function App() {
  const route = useRoute()
  const [backendUp, setBackendUp] = useState<boolean | null>(null)

  // Poll the backend until it answers, so the "unreachable" banner clears on
  // its own if the frontend was started first.
  useEffect(() => {
    let cancelled = false
    let timer: number | undefined
    const check = () => {
      getHealth()
        .then(() => !cancelled && setBackendUp(true))
        .catch(() => {
          if (cancelled) return
          setBackendUp(false)
          timer = window.setTimeout(check, 3000)
        })
    }
    check()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [])

  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="#/search">
          AI Research Assistant
        </a>
        <nav className="tabs">
          <a className={route.name === 'search' ? 'tab active' : 'tab'} href="#/search">
            Search
          </a>
          <a
            className={route.name === 'library' || route.name === 'paper' ? 'tab active' : 'tab'}
            href="#/library"
          >
            Library
          </a>
        </nav>
      </header>

      {backendUp === false && (
        <div className="banner error">
          Cannot reach the backend. Start it with <code>uv run uvicorn app.main:app</code> in{' '}
          <code>backend/</code>.
        </div>
      )}

      <main className="content">
        {route.name === 'search' && <SearchPage />}
        {route.name === 'library' && <LibraryPage />}
        {route.name === 'paper' && <PaperPage id={route.id} />}
      </main>
    </div>
  )
}
