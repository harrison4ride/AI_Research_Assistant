import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { errorResponse, mockFetch, ndjson, openStream } from '../test/fetchMock'
import { config, message } from '../test/fixtures'
import type { AppConfig, ChatMessage } from '../types'
import ChatPanel from './ChatPanel'

const HISTORY: ChatMessage[] = [
  message({ id: 1, role: 'user', content: 'What problem does this paper address?' }),
  message({ id: 2, role: 'assistant', content: 'It replaces **recurrence** with attention.', model: 'claude-opus-5 via Claude Code', context: 'full_text' }),
]

function answerEvents(question: string, answer: string) {
  return [
    { type: 'meta', context: 'full_text', truncated: false },
    { type: 'text', text: answer },
    {
      type: 'done',
      messages: [
        message({ id: 10, role: 'user', content: question }),
        message({ id: 11, role: 'assistant', content: answer, model: 'claude-opus-5 via Claude Code', context: 'full_text' }),
      ],
    },
  ]
}

// The conversation as shown: one entry per bubble (the suggestion chips repeat some questions).
function bubbles(): string[] {
  return Array.from(document.querySelectorAll('.chat-log .bubble'), (b) => b.textContent ?? '')
}

function setup(history: ChatMessage[] = [], llm: AppConfig | null = config(), model: string | null = 'opus') {
  const api = mockFetch().on('GET', '/api/papers/5/chat', history)
  const user = userEvent.setup()
  render(<ChatPanel paperId={5} llm={llm} model={model} />)
  const textbox = screen.getByPlaceholderText('Ask about this paper (Enter to send)')
  return { api, user, textbox }
}

describe('ChatPanel', () => {
  it('shows the earlier conversation', async () => {
    setup(HISTORY)

    await waitFor(() =>
      expect(bubbles()).toEqual([
        'What problem does this paper address?',
        'It replaces recurrence with attention.claude-opus-5 via Claude Code',
      ]),
    )
    expect(screen.getByText('recurrence').tagName).toBe('STRONG') // answers are Markdown
    expect(screen.getByText('claude-opus-5 via Claude Code')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Clear conversation' })).toBeInTheDocument()
  })

  it('labels answers that only had the abstract', async () => {
    setup([message({ id: 3, role: 'assistant', content: 'Probably ImageNet.', model: 'opus', context: 'abstract' })])

    expect(await screen.findByText('opus · based on the abstract only')).toBeInTheDocument()
  })

  it('asks a typed question with Enter and streams the answer', async () => {
    const { api, user, textbox } = setup([], config(), 'sonnet')
    const stream = openStream()
    api.on('POST', '/api/papers/5/chat', stream.response)

    await user.type(textbox, 'What datasets are used?{Enter}')

    expect(textbox).toHaveValue('')
    expect(bubbles()).toEqual(['What datasets are used?', 'Reading the paper…'])
    expect(screen.getByRole('button', { name: 'Answering…' })).toBeDisabled()
    expect(api.callsTo('POST', '/api/papers/5/chat')[0].body).toEqual({ question: 'What datasets are used?', model: 'sonnet' })

    for (const event of answerEvents('What datasets are used?', 'WMT 2014 English-German.')) stream.send(event)
    stream.close()

    await waitFor(() =>
      expect(bubbles()).toEqual(['What datasets are used?', 'WMT 2014 English-German.claude-opus-5 via Claude Code']),
    )
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled() // the input is empty again
  })

  it('keeps Shift+Enter for a new line', async () => {
    const { api, user, textbox } = setup()

    await user.type(textbox, 'First line{Shift>}{Enter}{/Shift}second line')

    expect(textbox).toHaveValue('First line\nsecond line')
    expect(api.callsTo('POST', '/api/papers/5/chat')).toHaveLength(0)
  })

  it('asks a suggested question with one click', async () => {
    const { api, user } = setup()
    api.on('POST', '/api/papers/5/chat', ndjson(answerEvents('What are the major limitations?', 'It needs lots of data.')))

    await user.click(screen.getByRole('button', { name: 'What are the major limitations?' }))

    await waitFor(() => expect(bubbles()[0]).toBe('What are the major limitations?'))
    expect(bubbles()[1]).toContain('It needs lots of data.')
    expect(api.callsTo('POST', '/api/papers/5/chat')[0].body).toMatchObject({ question: 'What are the major limitations?' })
  })

  it('cannot send an empty question', async () => {
    const { api, user, textbox } = setup()

    await user.type(textbox, '   {Enter}')

    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled()
    expect(api.callsTo('POST', '/api/papers/5/chat')).toHaveLength(0)
  })

  it('shows a failed answer and gives the question back', async () => {
    const { api, user, textbox } = setup()
    api.on(
      'POST',
      '/api/papers/5/chat',
      ndjson([
        { type: 'meta', context: 'full_text', truncated: false },
        { type: 'error', message: 'Claude Code is installed but not logged in. Run `claude auth login` in a terminal.' },
      ]),
    )

    await user.type(textbox, 'Why does it work?{Enter}')

    const alert = await screen.findByText(/Claude Code is installed but not logged in/)
    expect(within(alert).getByText('claude auth login').tagName).toBe('CODE')
    expect(textbox).toHaveValue('Why does it work?')
    expect(screen.queryByText('Reading the paper…')).not.toBeInTheDocument()
  })

  it('reports an unreachable backend', async () => {
    const { user, textbox } = setup()
    // The history loaded; now the backend goes away.
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await user.type(textbox, 'Hello?{Enter}')

    expect(await screen.findByText('Network error: cannot reach the backend.')).toBeInTheDocument()
    expect(textbox).toHaveValue('Hello?')
  })

  it('clears the conversation after confirmation', async () => {
    const { api, user } = setup(HISTORY)
    api.on('DELETE', '/api/papers/5/chat', new Response(null, { status: 204 }))
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    await user.click(await screen.findByRole('button', { name: 'Clear conversation' }))

    await waitFor(() => expect(bubbles()).toEqual([]))
    expect(api.callsTo('DELETE', '/api/papers/5/chat')).toHaveLength(1)
    expect(screen.queryByRole('button', { name: 'Clear conversation' })).not.toBeInTheDocument()
  })

  it('keeps the conversation when clearing is cancelled', async () => {
    const { api, user } = setup(HISTORY)
    vi.spyOn(window, 'confirm').mockReturnValue(false)

    await user.click(await screen.findByRole('button', { name: 'Clear conversation' }))

    expect(api.callsTo('DELETE', '/api/papers/5/chat')).toHaveLength(0)
    expect(bubbles()).toHaveLength(2)
  })

  it('shows an error when the conversation cannot be loaded', async () => {
    mockFetch().on('GET', '/api/papers/5/chat', errorResponse(404, 'Paper not found.'))
    render(<ChatPanel paperId={5} llm={config()} model="opus" />)

    expect(await screen.findByText('Paper not found.')).toBeInTheDocument()
  })

  it('is disabled with an explanation when the LLM is unavailable', async () => {
    const { textbox } = setup([], config({ llm_ready: false, llm_hint: 'Claude Code (the `claude` command) was not found.' }))

    expect(await screen.findByText('Summaries and Q&A are unavailable.')).toBeInTheDocument()
    expect(textbox).toBeDisabled()
    expect(screen.getByRole('button', { name: 'What datasets are used?' })).toBeDisabled()
  })
})
