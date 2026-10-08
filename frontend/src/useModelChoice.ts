import { useState } from 'react'
import type { AppConfig } from './types'

const STORAGE_KEY = 'llm-model'

function stored(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

// The model picked in the reader's menu, remembered in this browser. Falls back
// to the server's default when nothing (or a model no longer offered) is stored.
export function useModelChoice(llm: AppConfig | null): [string | null, (id: string) => void] {
  const [picked, setPicked] = useState<string | null>(stored)
  const offered = llm?.llm_models.map((m) => m.id) ?? []
  const model = picked && offered.includes(picked) ? picked : (llm?.llm_default_model ?? null)

  function choose(id: string) {
    setPicked(id)
    try {
      localStorage.setItem(STORAGE_KEY, id)
    } catch {
      // Storage unavailable: the choice lasts for this page only.
    }
  }
  return [model, choose]
}
