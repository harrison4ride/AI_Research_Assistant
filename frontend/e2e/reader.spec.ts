import { expect, test } from '@playwright/test'
import { RAG, ask, emptyLibrary, search } from './support/app'

test.beforeEach(async ({ request }) => {
  await emptyLibrary(request)
})

test('open a search result without saving it, ask about it, then save it', async ({ page }) => {
  await page.goto('/')
  await search(page, 'retrieval augmented generation')
  await page.getByRole('article').filter({ hasText: RAG }).getByRole('button', { name: 'Read' }).click()

  await expect(page).toHaveURL(/#\/paper\/\d+$/)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(RAG)
  // The result has no open-access PDF, so the assistant reads the abstract.
  await expect(page.getByText('Only the abstract is available.')).toBeVisible()
  await expect(page.getByText('No open-access PDF link is known for this paper.')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Search', exact: true })).toHaveClass(/active/)

  await ask(page, 'What problem does this paper address?')
  await expect(page.locator('.chat-log')).toContainText('from the abstract only')
  await expect(page.locator('.chat-log')).toContainText('based on the abstract only')

  // Not in the library until it is saved.
  const readerUrl = page.url()
  await page.getByRole('link', { name: 'Library', exact: true }).click()
  await expect(page.getByText('0 papers')).toBeVisible()
  await page.goto(readerUrl)

  await page.getByRole('button', { name: 'Save to library' }).click()
  await expect(page.getByText('✓ In library')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Library', exact: true })).toHaveClass(/active/)
  await expect(page.locator('.chat-log .bubble')).toHaveCount(2) // the conversation was kept

  await page.getByRole('link', { name: 'Library', exact: true }).click()
  await expect(page.getByRole('article')).toContainText(RAG)
})

test('a paper that no longer exists', async ({ page }) => {
  await page.goto('/#/paper/999999')

  await expect(page.getByText('This paper is no longer available.')).toBeVisible()
})

test('the model menu changes the model that answers', async ({ page }) => {
  await page.goto('/')
  await search(page, 'retrieval augmented generation')
  await page.getByRole('article').filter({ hasText: RAG }).getByRole('button', { name: 'Read' }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(RAG)

  await page.locator('.model-select select').selectOption('haiku')
  const request = page.waitForRequest((r) => r.url().endsWith('/chat') && r.method() === 'POST')
  await ask(page, 'Which model answers?')

  expect((await request).postDataJSON()).toEqual({ question: 'Which model answers?', model: 'haiku' })
  await expect(page.locator('.chat-log')).toContainText('Fake answer to “Which model answers?”')
})
