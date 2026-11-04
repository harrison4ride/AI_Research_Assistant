import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { deferred, errorResponse, jsonResponse, mockFetch } from '../test/fetchMock'
import { paper, pdfFile } from '../test/fixtures'
import type { Paper } from '../types'
import FullTextStatus from './FullTextStatus'

function setup(current: Paper, quietWhenOk = false) {
  const api = mockFetch()
  const onChange = vi.fn()
  const user = userEvent.setup()
  const view = render(<FullTextStatus paper={current} onChange={onChange} quietWhenOk={quietWhenOk} />)
  return { api, user, onChange, view }
}

const withPdf = paper({ id: 2, has_pdf: true, page_count: 12, full_text_status: 'ok', full_text_error: null })

describe('FullTextStatus', () => {
  it('downloads the PDF the first time a paper is viewed', async () => {
    const api = mockFetch()
    const pending = deferred()
    api.on('POST', '/api/papers/2/fulltext', pending.reply)
    const onChange = vi.fn()
    render(<FullTextStatus paper={paper({ id: 2, full_text_status: null, full_text_error: null })} onChange={onChange} />)

    expect(screen.getByText('Downloading and reading the PDF…')).toBeInTheDocument()
    pending.resolve(jsonResponse({ ...withPdf, title: 'A stale title from the server' }))

    // Only the full-text fields are passed on, so edits made meanwhile are kept.
    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith({ has_pdf: true, page_count: 12, full_text_status: 'ok', full_text_error: null }),
    )
    expect(api.callsTo('POST', '/api/papers/2/fulltext')[0].query.get('retry')).toBeNull()
  })

  it('says the whole paper is available', () => {
    setup(withPdf)
    expect(screen.getByText(/Full text available \(12 pages\)\. The assistant reads the whole paper\./)).toBeInTheDocument()
  })

  it('stays quiet when the PDF is shown anyway', () => {
    const { view } = setup(withPdf, true)
    expect(view.container).toBeEmptyDOMElement()
  })

  it('explains an abstract-only paper and offers to attach a PDF', () => {
    setup(paper({ full_text_status: 'unavailable', full_text_error: 'No open-access PDF link is known for this paper.' }))

    expect(screen.getByText('Only the abstract is available.')).toBeInTheDocument()
    expect(screen.getByText(/No open-access PDF link is known for this paper\./)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Attach PDF' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retry download' })).not.toBeInTheDocument()
  })

  it('retries a failed download', async () => {
    const { api, user, onChange } = setup(paper({ id: 2, full_text_status: 'error', full_text_error: 'The PDF link returned HTTP 503.' }))
    api.on('POST', '/api/papers/2/fulltext', withPdf)

    await user.click(screen.getByRole('button', { name: 'Retry download' }))

    await waitFor(() => expect(onChange).toHaveBeenCalled())
    expect(api.callsTo('POST', '/api/papers/2/fulltext')[0].query.get('retry')).toBe('true')
  })

  it('attaches a PDF the user has', async () => {
    const { api, user, onChange } = setup(paper({ id: 2, full_text_status: 'unavailable' }))
    api.on('POST', '/api/papers/2/pdf', withPdf)

    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, pdfFile('bert.pdf'))

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ full_text_status: 'ok' })))
    const form = api.callsTo('POST', '/api/papers/2/pdf')[0].body as FormData
    expect((form.get('file') as File).name).toBe('bert.pdf')
  })

  it('shows why an attached file was refused', async () => {
    const { api, user } = setup(paper({ id: 2, full_text_status: 'unavailable' }))
    api.on('POST', '/api/papers/2/pdf', errorResponse(415, 'The file is not a PDF.'))

    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, pdfFile('fake.pdf'))

    expect(await screen.findByText('The file is not a PDF.')).toBeInTheDocument()
  })

  it('offers a retry when the first download request fails', async () => {
    const api = mockFetch().on('POST', '/api/papers/2/fulltext', errorResponse(500, 'Internal Server Error'))
    render(<FullTextStatus paper={paper({ id: 2, full_text_status: null })} onChange={vi.fn()} />)

    expect(await screen.findByText('Internal Server Error')).toBeInTheDocument()
    api.on('POST', '/api/papers/2/fulltext', withPdf)
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))

    await waitFor(() => expect(api.callsTo('POST', '/api/papers/2/fulltext')).toHaveLength(2))
    expect(api.callsTo('POST', '/api/papers/2/fulltext')[1].query.get('retry')).toBe('true')
  })
})
