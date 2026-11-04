import { expect, test } from '@playwright/test'
import { RAG, RAG_ABSTRACT_END, ask, expectTabMarked, paperId, resetApp, search } from './support/app'

test.beforeEach(async ({ request }) => {
  await resetApp(request)
})

test('open a search result without saving it, ask about it, then save it', async ({ page, request }) => {
  await page.goto('/')
  await search(page, 'retrieval augmented generation')
  await page.getByRole('article').filter({ hasText: RAG }).getByRole('button', { name: 'Read' }).click()

  await expect(page).toHaveURL(/#\/paper\/\d+$/)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(RAG)
  // The result has no open-access PDF, so the assistant reads the abstract.
  await expect(page.getByText('Only the abstract is available.')).toBeVisible()
  await expect(page.getByText('No open-access PDF link is known for this paper.')).toBeVisible()
  await expectTabMarked(page, 'Search') // an unsaved paper belongs to the search page

  await ask(page, 'What problem does this paper address?')
  const log = page.locator('.chat-log')
  // The fake Claude Code reports the end of the paper text it was given: the abstract's.
  await expect(log).toContainText(`The paper text ends with “${RAG_ABSTRACT_END}”`)
  await expect(log).toContainText('based on the abstract only') // shown once the answer is saved

  // Not in the library until it is saved.
  const readerUrl = page.url()
  await page.getByRole('link', { name: 'Library', exact: true }).click()
  await expect(page.getByText('0 papers')).toBeVisible()
  await page.goto(readerUrl)

  await page.getByRole('button', { name: 'Save to library' }).click()
  await expect(page.getByText('✓ In library')).toBeVisible()
  await expectTabMarked(page, 'Library')

  // Saved with its conversation: after a reload, and on the server.
  await page.reload()
  await expect(page.getByText('✓ In library')).toBeVisible()
  await expect(page.locator('.chat-log .bubble')).toHaveCount(2)
  await expect(page.locator('.chat-log .bubble').first()).toHaveText('What problem does this paper address?')
  const chat: { role: string }[] = await (await request.get(`/api/papers/${paperId(page)}/chat`)).json()
  expect(chat.map((message) => message.role)).toEqual(['user', 'assistant'])

  await page.getByRole('link', { name: 'Library', exact: true }).click()
  await expect(page.getByRole('article')).toHaveCount(1)
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

  await page.getByRole('combobox', { name: /Model/ }).selectOption('haiku')
  const request = page.waitForRequest((r) => r.url().endsWith('/chat') && r.method() === 'POST')
  await ask(page, 'Which model answers?')

  expect((await request).postDataJSON()).toEqual({ question: 'Which model answers?', model: 'haiku' })
  // The fake Claude Code reports the model it was started with; the answer names it.
  await expect(page.locator('.chat-log')).toContainText('claude-fake-haiku via Claude Code')

  // The browser remembers the choice.
  await page.reload()
  await expect(page.getByRole('combobox', { name: /Model/ })).toHaveValue('haiku')
})
