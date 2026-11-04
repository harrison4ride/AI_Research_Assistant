import { expect, test } from '@playwright/test'
import { DPR, RAG, expectTabMarked, resetApp, search } from './support/app'

test.beforeEach(async ({ request }) => {
  await resetApp(request)
})

test('search for papers, save one, and find it in the library after a reload', async ({ page }) => {
  await page.goto('/')
  await search(page, 'retrieval augmented generation')

  await expect(page.getByText('Showing 2 of 2 results for “retrieval augmented generation” from OpenAlex')).toBeVisible()
  const card = page.getByRole('article').filter({ hasText: RAG })
  await expect(card.getByText('Patrick Lewis, Ethan Perez, Aleksandra Piktus')).toBeVisible()
  await expect(card.getByText('2020', { exact: true })).toBeVisible()
  await expect(card.getByText(/Large pre-trained language models have been shown/)).toBeVisible()
  await expect(card.getByRole('link', { name: 'View paper ↗' })).toHaveAttribute('href', 'https://arxiv.org/abs/2005.11401')

  await card.getByRole('button', { name: 'Save to library' }).click()
  await expect(card.getByText('✓ Saved')).toBeVisible()

  await page.getByRole('link', { name: 'Library', exact: true }).click()
  await expect(page.getByText('1 paper', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('article')).toHaveCount(1)
  await expect(page.getByRole('article')).toContainText(RAG)

  // Back on the search page the result is still marked as saved.
  await page.getByRole('link', { name: 'Search', exact: true }).click()
  await expect(page.getByRole('article').filter({ hasText: RAG }).getByText('✓ Saved')).toBeVisible()
  await expect(page.getByRole('article').filter({ hasText: DPR }).getByRole('button', { name: 'Save to library' })).toBeVisible()
})

test('filter the library and remove a paper', async ({ page, request }) => {
  await page.goto('/')
  await search(page, 'dense retrieval')
  for (const title of [RAG, DPR]) {
    const card = page.getByRole('article').filter({ hasText: title })
    await card.getByRole('button', { name: 'Save to library' }).click()
    await expect(card.getByText('✓ Saved')).toBeVisible()
  }

  await page.getByRole('link', { name: 'Library', exact: true }).click()
  await expect(page.getByText('2 papers')).toBeVisible()
  await expectTabMarked(page, 'Library')
  await page.getByPlaceholder('Filter by title, author, or abstract').fill('oğuz') // an author, not ASCII
  await expect(page.getByText('1 paper matching')).toBeVisible()
  await expect(page.getByRole('article')).toContainText(DPR)

  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('article').getByRole('button', { name: 'Remove' }).click()
  await expect(page.getByText('No saved papers match “oğuz”.')).toBeVisible()

  // Removed on the server, not only on the page: a reload and the API agree.
  await page.reload()
  await expect(page.getByText('1 paper', { exact: true })).toBeVisible()
  await expect(page.getByRole('article')).toHaveCount(1)
  await expect(page.getByRole('article')).toContainText(RAG)
  const library: { title: string }[] = await (await request.get('/api/papers')).json()
  expect(library.map((paper) => paper.title)).toEqual([RAG])
})

test('search arXiv and open a result whose PDF link is not public', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('combobox', { name: 'Search source' }).selectOption('arxiv')
  await search(page, 'attention is all you need')

  await expect(page.getByText(/Showing 1 of 1 results for “attention is all you need” from arXiv/)).toBeVisible()
  const card = page.getByRole('article')
  await expect(card.getByRole('link', { name: 'Attention Is All You Need' })).toBeVisible()
  await expect(card.getByText('Ashish Vaswani, Noam Shazeer, Niki Parmar')).toBeVisible()
  await expect(card.getByText('NeurIPS 2017')).toBeVisible()
  // The fake arXiv entry links its PDF on a documentation-only address (see e2e_server.py).
  await expect(card.getByRole('link', { name: 'PDF ↗' })).toHaveAttribute('href', 'http://192.0.2.10/pdf/1706.03762v7')

  await card.getByRole('button', { name: 'Read' }).click()

  // README: PDFs are downloaded "only from public http(s) addresses"; the reader says why
  // it falls back to the abstract and offers to attach the PDF.
  await expect(page.getByText('Only the abstract is available.')).toBeVisible()
  await expect(page.getByText(/The PDF link points to a local or private address, so it was not downloaded\./)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Attach PDF' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Abstract' })).toBeVisible()
})

test('failed and empty searches are explained', async ({ page }) => {
  await page.goto('/')

  await search(page, 'fake-500 please')
  await expect(page.getByText('OpenAlex returned HTTP 500.')).toBeVisible()

  await search(page, 'fake-empty')
  await expect(page.getByText('No results for “fake-empty”.')).toBeVisible()
  await expect(page.getByText('OpenAlex returned HTTP 500.')).toBeHidden()
})
