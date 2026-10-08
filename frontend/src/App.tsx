import { useEffect, useState } from 'react'
import { getHealth } from './api'
import { useRoute } from './router'
import SearchPage from './pages/SearchPage'
import LibraryPage from './pages/LibraryPage'
import PaperPage from './pages/PaperPage'

export default function App() {
  const route = useRoute()
  const [backendUp, setBackendUp] = useState<boolean | null>(null)
  // Whether the open paper is in the library (an unsaved one belongs to Search);
  // null until the paper has loaded, so no tab is claimed meanwhile.
  const [paperInLibrary, setPaperInLibrary] = useState<{ id: number; inLibrary: boolean } | null>(null)
  const openPaper = route.name === 'paper' && paperInLibrary?.id === route.id ? paperInLibrary : null
  const onPaperSearchTab = openPaper?.inLibrary === false
  const onPaperLibraryTab = openPaper?.inLibrary === true

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
          <a className={route.name === 'search' || onPaperSearchTab ? 'tab active' : 'tab'} href="#/search">
            Search
          </a>
          <a
            className={route.name === 'library' || onPaperLibraryTab ? 'tab active' : 'tab'}
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

      <main className={route.name === 'paper' ? 'content wide' : 'content'}>
        {route.name === 'search' && <SearchPage />}
        {route.name === 'library' && <LibraryPage />}
        {/* key: remount per paper so no state leaks between papers */}
        {route.name === 'paper' && (
          <PaperPage
            key={route.id}
            id={route.id}
            onLibraryState={(inLibrary) => setPaperInLibrary({ id: route.id, inLibrary })}
          />
        )}
      </main>
    </div>
  )
}
