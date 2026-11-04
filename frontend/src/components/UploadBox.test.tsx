import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { deferred, errorResponse, jsonResponse, mockFetch } from '../test/fetchMock'
import { paper, pdfFile } from '../test/fixtures'
import UploadBox from './UploadBox'

function setup() {
  const onUploaded = vi.fn()
  const api = mockFetch()
  // applyAccept: false lets a test pick a non-PDF despite the input's accept filter, as a user can.
  const user = userEvent.setup({ applyAccept: false })
  render(<UploadBox onUploaded={onUploaded} />)
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  return { api, user, input, onUploaded }
}

describe('UploadBox', () => {
  it('opens the file picker from the Upload PDF button', async () => {
    const { user, input } = setup()
    const click = vi.spyOn(input, 'click')

    await user.click(screen.getByRole('button', { name: 'Upload PDF' }))

    expect(click).toHaveBeenCalled()
    expect(input).toHaveAttribute('accept', 'application/pdf,.pdf')
  })

  it('uploads the chosen PDF and reports the new paper', async () => {
    const { api, user, input, onUploaded } = setup()
    const uploaded = paper({ id: 12, source: 'upload', title: 'Extracted Title' })
    api.on('POST', '/api/papers/upload', jsonResponse(uploaded, 201))

    await user.upload(input, pdfFile('retrieval.pdf'))

    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith(uploaded))
    const form = api.callsTo('POST', '/api/papers/upload')[0].body as FormData
    expect((form.get('file') as File).name).toBe('retrieval.pdf')
  })

  it('shows progress while the PDF is read', async () => {
    const { api, user, input } = setup()
    const pending = deferred()
    api.on('POST', '/api/papers/upload', pending.reply)

    await user.upload(input, pdfFile('long-paper.pdf'))

    expect(screen.getByText(/Uploading and reading/)).toHaveTextContent('Uploading and reading long-paper.pdf…')
    expect(screen.queryByRole('button', { name: 'Upload PDF' })).not.toBeInTheDocument()
    pending.resolve(jsonResponse(paper({ id: 1 }), 201))
    expect(await screen.findByRole('button', { name: 'Upload PDF' })).toBeInTheDocument()
  })

  it('refuses files that are not PDFs without uploading them', async () => {
    const { api, user, input, onUploaded } = setup()

    await user.upload(input, new File(['hello'], 'notes.txt', { type: 'text/plain' }))

    expect(await screen.findByText('Please choose a PDF file.')).toBeInTheDocument()
    expect(api.calls).toHaveLength(0)
    expect(onUploaded).not.toHaveBeenCalled()
  })

  it('accepts a PDF whose name lacks the extension', async () => {
    const { api, user, input, onUploaded } = setup()
    api.on('POST', '/api/papers/upload', jsonResponse(paper({ id: 3 }), 201))

    await user.upload(input, new File(['%PDF-1.7'], 'download', { type: 'application/pdf' }))

    await waitFor(() => expect(onUploaded).toHaveBeenCalled())
  })

  it('shows the reason the backend rejected the file', async () => {
    const { api, user, input, onUploaded } = setup()
    api.on('POST', '/api/papers/upload', errorResponse(422, 'The PDF is password-protected.'))

    await user.upload(input, pdfFile('locked.pdf'))

    expect(await screen.findByText('The PDF is password-protected.')).toBeInTheDocument()
    expect(onUploaded).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Upload PDF' })).toBeInTheDocument()
  })

  it('uploads a PDF dropped onto it', async () => {
    const { api, onUploaded } = setup()
    const uploaded = paper({ id: 4, source: 'upload' })
    api.on('POST', '/api/papers/upload', jsonResponse(uploaded, 201))
    // Dropped on the button, the file reaches the drop zone around it ("or drop a paper here").
    const target = screen.getByRole('button', { name: 'Upload PDF' })

    fireEvent.dragOver(target)
    fireEvent.drop(target, { dataTransfer: { files: [pdfFile('dropped.pdf')] } })

    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith(uploaded))
    const form = api.callsTo('POST', '/api/papers/upload')[0].body as FormData
    expect((form.get('file') as File).name).toBe('dropped.pdf')
  })

  it('refuses a dropped file that is not a PDF', async () => {
    const { api, onUploaded } = setup()

    fireEvent.drop(screen.getByRole('button', { name: 'Upload PDF' }), {
      dataTransfer: { files: [new File(['hello'], 'notes.txt', { type: 'text/plain' })] },
    })

    expect(await screen.findByText('Please choose a PDF file.')).toBeInTheDocument()
    expect(api.calls).toHaveLength(0)
    expect(onUploaded).not.toHaveBeenCalled()
  })
})
