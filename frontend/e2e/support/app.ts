import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import type { APIRequestContext, Page } from '@playwright/test'

const backendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../backend')

// The sample paper (backend/tests/support/pdfs.py) and what extraction should find in it.
export const SAMPLE = {
  title: 'Retrieval Helps Language Models Stay Factual',
  authors: 'Alice Smith, Bob Jones, Carol White',
  year: '2023',
  abstractStart: 'We study how retrieving external documents improves the factual accuracy',
}

let samplePdf: Buffer | undefined

// A PDF file for upload, built with PyMuPDF by the backend's test helpers.
export function samplePaper(name = 'retrieval.pdf') {
  samplePdf ??= execFileSync('uv', ['run', '--quiet', 'python', 'tests/support/pdfs.py', 'sample'], {
    cwd: backendDir,
  })
  return { name, mimeType: 'application/pdf', buffer: samplePdf }
}

// The fake OpenAlex (backend/tests/support/e2e_server.py) returns these two papers.
export const RAG = 'Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks'
export const DPR = 'Dense Passage Retrieval for Open-Domain Question Answering'

// Tests share one app and database: each starts from an empty library.
export async function emptyLibrary(request: APIRequestContext) {
  const papers: { id: number }[] = await (await request.get('/api/papers')).json()
  for (const paper of papers) await request.delete(`/api/papers/${paper.id}`)
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
