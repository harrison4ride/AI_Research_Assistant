import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { deferred, errorResponse, jsonResponse, mockFetch } from '../test/fetchMock'
import { config, outline, paper } from '../test/fixtures'
import type { AppConfig, Outline } from '../types'
import SectionsPanel from './SectionsPanel'

const reader = paper({ id: 3, has_pdf: true, full_text_status: 'ok' })

function setup(current: Outline = outline(), { position = 1, llm = config() }: { position?: number; llm?: AppConfig } = {}) {
  const api = mockFetch().on('GET', '/api/papers/3/outline', current)
  const onJump = vi.fn()
  const user = userEvent.setup()
  render(<SectionsPanel paper={reader} llm={llm} model="sonnet" position={position} onJump={onJump} />)
  return { api, user, onJump }
}

function sectionItem(title: string): HTMLElement {
  return screen.getByText(title).closest('li')!
}

describe('SectionsPanel', () => {
  it('lists the sections with their pages', async () => {
    setup()

    expect(screen.getByText("Reading the paper's structure…")).toBeInTheDocument()
    expect(await screen.findByText('1 Introduction')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      '1 Introductionp. 1',
      '2 Methodp. 2',
      '2.1 Retrieverp. 2',
    ])
    expect(sectionItem('2.1 Retriever')).toHaveClass('level-2')
  })

  it('jumps to a section in the PDF', async () => {
    const { user, onJump } = setup()

    await user.click(await screen.findByRole('button', { name: /2 Method/ }))

    expect(onJump).toHaveBeenCalledWith(2, 0.1)
  })

  it('cannot jump to a section that was not found in the PDF', async () => {
    const { onJump } = setup(outline({ sections: [{ level: 1, title: 'Appendix', page: null, top: null, summary: null }] }))

    const button = await screen.findByRole('button', { name: 'Appendix' })

    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('title', 'Not found in the PDF')
    expect(onJump).not.toHaveBeenCalled()
  })

  it('highlights the section being read', async () => {
    setup(outline(), { position: 2.3 })

    await screen.findByText('2 Method')

    expect(sectionItem('2 Method')).toHaveClass('active')
    expect(sectionItem('1 Introduction')).not.toHaveClass('active')
    expect(sectionItem('2.1 Retriever')).not.toHaveClass('active')
  })

  it('writes one-sentence summaries on request', async () => {
    const { api, user } = setup()
    const pending = deferred()
    api.on('POST', '/api/papers/3/outline/summaries', pending.reply)

    await user.click(await screen.findByRole('button', { name: 'Summarize sections' }))
    expect(screen.getByRole('button', { name: 'Summarizing…' })).toBeDisabled()
    pending.resolve(
      jsonResponse(
        outline({
          summarized: true,
          model: 'claude-sonnet-5 via Claude Code',
          sections: outline().sections.map((s) => ({ ...s, summary: `What ${s.title} says.` })),
        }),
      ),
    )

    expect(await screen.findByText('What 2 Method says.')).toBeInTheDocument()
    expect(screen.getByText('by claude-sonnet-5 via Claude Code')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Regenerate summaries' })).toBeEnabled()
    expect(api.callsTo('POST', '/api/papers/3/outline/summaries')[0].body).toEqual({ model: 'sonnet' })
  })

  it('shows why the summaries failed', async () => {
    const { api, user } = setup()
    api.on(
      'POST',
      '/api/papers/3/outline/summaries',
      errorResponse(502, "The model's reply skipped 1 of 3 sections, so it was not saved. Try again."),
    )

    await user.click(await screen.findByRole('button', { name: 'Summarize sections' }))

    expect(await screen.findByText(/skipped 1 of 3 sections/)).toBeInTheDocument()
    expect(screen.getByText('1 Introduction')).toBeInTheDocument() // the outline is still shown
  })

  it('explains a paper without headings', async () => {
    setup(outline({ sections: [] }))

    expect(await screen.findByText(/No section headings were found in this PDF/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Summarize sections' })).toBeEnabled()
  })

  it('explains why there is no outline', async () => {
    setup(outline({ available: false, reason: "The outline needs the paper's PDF.", sections: [] }))

    expect(await screen.findByText("The outline needs the paper's PDF.")).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Summarize sections' })).not.toBeInTheDocument()
  })

  it('cannot summarize while the LLM is unavailable', async () => {
    setup(outline(), { llm: config({ llm_ready: false, llm_hint: 'Log in.' }) })

    expect(await screen.findByRole('button', { name: 'Summarize sections' })).toBeDisabled()
  })

  it('shows an error when the outline cannot be loaded', async () => {
    mockFetch().on('GET', '/api/papers/3/outline', errorResponse(404, 'Paper not found.'))
    render(<SectionsPanel paper={reader} llm={config()} model={null} position={1} onJump={vi.fn()} />)

    await waitFor(() => expect(screen.getByText('Paper not found.')).toBeInTheDocument())
  })
})
