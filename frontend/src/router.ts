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
        window.history.replaceState(null, '', canonicalHash(next))
      }
      setRoute(next)
    }
    onChange()
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}
