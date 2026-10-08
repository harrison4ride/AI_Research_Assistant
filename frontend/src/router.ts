import { useEffect, useState } from 'react'

// Minimal hash router: keeps the current view in the URL so a page refresh
// lands the user back where they were (e.g. #/paper/12).
export type Route =
  | { name: 'search' }
  | { name: 'library' }
  | { name: 'paper'; id: number }

export function parseHash(hash: string): Route {
  const path = hash.replace(/^#/, '').replace(/\/+$/, '')
  const paper = path.match(/^\/paper\/(\d+)$/)
  if (paper) return { name: 'paper', id: Number(paper[1]) }
  if (path === '/library') return { name: 'library' }
  return { name: 'search' }
}

// Each history entry made inside the app records its depth (0 = the page the
// app was opened on). "Back" may use history.back() only above depth 0;
// browser back/forward restores the entry's own depth, so this stays correct.
function depth(): number {
  const state = window.history.state as { depth?: unknown } | null
  return typeof state?.depth === 'number' ? state.depth : 0
}

let lastDepth = 0

export function canGoBack(): boolean {
  return depth() > 0
}

function canonicalHash(route: Route): string {
  return route.name === 'paper' ? `#/paper/${route.id}` : `#/${route.name}`
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseHash(window.location.hash))
  useEffect(() => {
    const onChange = () => {
      const next = parseHash(window.location.hash)
      // Rewrite unknown or non-canonical hashes (e.g. trailing slash) so the
      // address bar always matches the page being shown.
      if (window.location.hash !== canonicalHash(next)) {
        window.history.replaceState(window.history.state, '', canonicalHash(next))
      }
      setRoute(next)
    }
    const onHashChange = () => {
      const state = window.history.state as { depth?: unknown } | null
      if (typeof state?.depth !== 'number') {
        // A new entry (link click or assignment): one level deeper than the last one.
        window.history.replaceState({ ...(state ?? {}), depth: lastDepth + 1 }, '')
      }
      lastDepth = depth()
      onChange()
    }
    if (typeof (window.history.state as { depth?: unknown } | null)?.depth !== 'number') {
      window.history.replaceState({ ...(window.history.state ?? {}), depth: 0 }, '')
    }
    lastDepth = depth()
    onChange()
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])
  return route
}
