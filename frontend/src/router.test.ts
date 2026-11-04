import { describe, expect, it } from 'vitest'
import { parseHash } from './router'
import { paperKey } from './types'
import { searchResult } from './test/fixtures'

describe('parseHash', () => {
  it.each([
    ['', { name: 'search' }],
    ['#/search', { name: 'search' }],
    ['#/library', { name: 'library' }],
    ['#/library/', { name: 'library' }],
    ['#/paper/12', { name: 'paper', id: 12 }],
    ['#/paper/12//', { name: 'paper', id: 12 }],
    ['#/paper/abc', { name: 'search' }],
    ['#/paper/', { name: 'search' }],
    ['#/settings', { name: 'search' }],
  ])('%s', (hash, route) => {
    expect(parseHash(hash)).toEqual(route)
  })
})

describe('paperKey', () => {
  it('identifies a search result by source and id', () => {
    expect(paperKey(searchResult({ source: 'arxiv', external_id: '1706.03762' }))).toBe('arxiv:1706.03762')
  })

  it('falls back to the URL, then the DOI, then the title', () => {
    expect(paperKey(searchResult({ external_id: null, url: 'https://x.org/a' }))).toBe('openalex:https://x.org/a')
    expect(paperKey(searchResult({ external_id: null, url: null, doi: '10.1/x' }))).toBe('openalex:10.1/x')
    expect(paperKey(searchResult({ external_id: null, url: null, doi: null, title: 'T' }))).toBe('openalex:T')
  })
})
