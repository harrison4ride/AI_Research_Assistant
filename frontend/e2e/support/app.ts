import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, type APIRequestContext, type Locator, type Page } from '@playwright/test'

const backendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../backend')

function pdfsScript(command: 'sample' | 'sections' | 'meta'): Buffer {
  return execFileSync('uv', ['run', '--quiet', 'python', 'tests/support/pdfs.py', command], { cwd: backendDir })
}

// What the sample paper (backend/tests/support/pdfs.py) contains, read from the script that
// writes it, so these tests and the PDF cannot drift apart.
export const SAMPLE: {
  title: string
  authors: string[]
  year: number
  abstract: string
  bodyMarker: string // a sentence only on page 2
  textEnd: string // the last words of the paper's text
  sections: string[]
  sectionPages: string[] // the five-page variant: one section per page
} = JSON.parse(pdfsScript('meta').toString())

const pdfs = new Map<string, Buffer>()

// A PDF file for upload, built with PyMuPDF by the backend's test helpers.
export function samplePaper(name = 'retrieval.pdf', variant: 'sample' | 'sections' = 'sample') {
  if (!pdfs.has(variant)) pdfs.set(variant, pdfsScript(variant))
  return { name, mimeType: 'application/pdf', buffer: pdfs.get(variant)! }
}

// The fake OpenAlex (backend/tests/support/e2e_server.py) returns these two papers, without PDF links.
export const RAG = 'Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks'
export const RAG_ABSTRACT_END = 'a fine-tuning recipe for retrieval-augmented generation.'
export const DPR = 'Dense Passage Retrieval for Open-Domain Question Answering'

// Tests share one app and database. Each starts with no papers at all: neither saved ones
// nor ones that were only opened (with their conversations), and no cached searches.
export async function resetApp(request: APIRequestContext) {
  const response = await request.post('/__e2e__/reset')
  expect(response.status()).toBe(204)
}

export async function search(page: Page, query: string) {
  await page.getByRole('searchbox').fill(query)
  await page.getByRole('button', { name: 'Search', exact: true }).click()
}

export async function ask(page: Page, question: string) {
  const box = page.getByPlaceholder('Ask about this paper (Enter to send)')
  await box.fill(question)
  await box.press('Enter')
}

// The id of the paper open in the reader.
export function paperId(page: Page): number {
  const match = page.url().match(/#\/paper\/(\d+)$/)
  if (!match) throw new Error(`Not in the reader: ${page.url()}`)
  return Number(match[1])
}

// The app marks the current tab and the section being read only by how they look (a tinted
// background); there is no accessible marker. This reads what the user sees. Move the mouse
// away first: hovering a tab tints it too.
export async function isHighlighted(element: Locator): Promise<boolean> {
  return element.evaluate((el) => getComputedStyle(el).backgroundColor !== 'rgba(0, 0, 0, 0)')
}

export async function expectTabMarked(page: Page, marked: 'Search' | 'Library') {
  await page.mouse.move(0, 700)
  const other = marked === 'Search' ? 'Library' : 'Search'
  const tab = (name: string) => page.getByRole('navigation').getByRole('link', { name, exact: true })
  await expect.poll(() => isHighlighted(tab(marked))).toBe(true)
  expect(await isHighlighted(tab(other))).toBe(false)
}

// The list item of a section in the reader's Sections tab.
export function sectionItem(page: Page, title: string): Locator {
  return page.getByRole('listitem').filter({ has: page.getByRole('button', { name: new RegExp(`^${title}`) }) })
}

// Where `text` from the PDF is drawn, in pixels below the top of the PDF view.
export async function offsetInPdfView(page: Page, text: string): Promise<number> {
  const view = page.locator('.pdf-scroll')
  const line = view.getByText(text, { exact: true })
  const [viewBox, lineBox] = [await view.boundingBox(), await line.boundingBox()]
  if (!viewBox || !lineBox) throw new Error(`"${text}" is not laid out in the PDF view`)
  return lineBox.y - viewBox.y
}
