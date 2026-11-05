import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { deferred, errorResponse, jsonResponse, mockFetch } from '../test/fetchMock'
import { config, outline, paper } from '../test/fixtures'
import { useAppStylesheet } from '../test/stylesheet'
import type { AppConfig, Outline } from '../types'
import SectionsPanel from './SectionsPanel'

// How far the stylesheet moves an item in from the list's left edge (jsdom keeps the unit, rem).
function indent(item: HTMLElement): number {
  return parseFloat(getComputedStyle(item).marginLeft) || 0
}

const reader = paper({ id: 3, has_pdf: true, full_text_status: 'ok' })

function setup(current: Outline = outline(), { position = 1, llm = config() }: { position?: number; llm?: AppConfig } = {}) {
  const api = mockFetch().on('GET', '/api/papers/3/outline', current)
  const onJump = vi.fn()
  const user = userEvent.setup()
  render(<SectionsPanel paper={reader} llm={llm} model="sonnet" position={position} onJump={onJump} />)
  return { api, user, onJump }
}

// The panel marks the section being read only visually (class "active", styled in index.css);
// there is no accessible marker such as aria-current to read instead.
function sectionsBeingRead(): string[] {
  return screen
    .getAllByRole('listitem')
    .filter((item) => item.classList.contains('active'))
    .map((item) => within(item).getByRole('button').firstChild?.textContent ?? '')
}

const TWO_COLUMNS = outline({
  sections: [
    // A two-column paper lists the right column's heading after the left one's, though it starts higher.
    { level: 1, title: '3 Results', page: 4, top: 0.6, summary: null },
    { level: 1, title: '4 Discussion', page: 4, top: 0.2, summary: null },
    { level: 1, title: 'Appendix', page: null, top: null, summary: null },
  ],
})

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
    expect(screen.getByRole('button', { name: /2 Method/ })).toHaveAttribute('title', 'Go to page 2')
  })

  it('indents subsections under their section', async () => {
    useAppStylesheet()
    setup()

    // 1 Introduction, 2 Method, and its subsection 2.1 Retriever, in this order.
    const [introduction, method, retriever] = (await screen.findAllByRole('listitem')).map(indent)

    expect(method).toBe(introduction) // sections line up
    expect(retriever).toBeGreaterThan(method) // the subsection sits further right
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

  // The section being read starts furthest down, but at or above the reading position
  // (page + fraction of the page); at the end of the document it is the last section.
  it.each([
    [outline(), 1.1, []], // above the first heading
    [outline(), 1.3, ['1 Introduction']], // exactly where it starts
    [outline(), 2.05, ['1 Introduction']], // page 2, above its first heading
    [outline(), 2.3, ['2 Method']],
    [outline(), 2.75, ['2.1 Retriever']],
    [outline(), Number.POSITIVE_INFINITY, ['2.1 Retriever']], // scrolled to the end
    [TWO_COLUMNS, 4.3, ['4 Discussion']], // listed later, but the only one started
    [TWO_COLUMNS, 4.7, ['3 Results']], // both started: the one starting further down
    [TWO_COLUMNS, Number.POSITIVE_INFINITY, ['3 Results']], // a section without a page never counts
  ])('highlights the section being read (outline %#, position %f)', async (sections, position, expected) => {
    setup(sections, { position })

    await screen.findAllByRole('listitem')

    expect(sectionsBeingRead()).toEqual(expected)
  })

  it('reads the outline again when the paper gains a PDF', async () => {
    const api = mockFetch().on('GET', '/api/papers/3/outline', outline({ available: false, reason: "The outline needs the paper's PDF.", sections: [] }))
    const withoutPdf = paper({ id: 3, has_pdf: false, full_text_status: 'unavailable' })
    const props = { llm: config(), model: 'opus', position: 1, onJump: vi.fn() }
    const { rerender } = render(<SectionsPanel paper={withoutPdf} {...props} />)
    expect(await screen.findByText("The outline needs the paper's PDF.")).toBeInTheDocument()
    api.on('GET', '/api/papers/3/outline', outline())

    // E.g. the user attached the PDF.
    rerender(<SectionsPanel paper={{ ...withoutPdf, has_pdf: true, full_text_status: 'ok' }} {...props} />)

    expect(await screen.findByRole('button', { name: /2 Method/ })).toBeInTheDocument()
    expect(api.callsTo('GET', '/api/papers/3/outline')).toHaveLength(2)
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
