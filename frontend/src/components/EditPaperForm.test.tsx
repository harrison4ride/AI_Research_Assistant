import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { errorResponse, jsonResponse, mockFetch } from '../test/fetchMock'
import { paper } from '../test/fixtures'
import EditPaperForm from './EditPaperForm'

// Typically used to correct metadata that was extracted from an uploaded PDF.
const extracted = paper({ id: 6, source: 'upload', title: 'Retrieval Helps Language Models', authors: ['Alice Smith', 'Bob Jones'], year: 2023, abstract: 'We study retrieval.' })

function setup() {
  const api = mockFetch()
  const onSaved = vi.fn()
  const onCancel = vi.fn()
  const user = userEvent.setup()
  render(<EditPaperForm paper={extracted} onSaved={onSaved} onCancel={onCancel} />)
  return { api, user, onSaved, onCancel }
}

describe('EditPaperForm', () => {
  it('starts with the current metadata, one author per line', () => {
    setup()

    expect(screen.getByRole('textbox', { name: 'Title' })).toHaveValue('Retrieval Helps Language Models')
    expect(screen.getByRole('textbox', { name: /Authors/ })).toHaveValue('Alice Smith\nBob Jones')
    expect(screen.getByRole('spinbutton', { name: 'Year' })).toHaveValue(2023)
    expect(screen.getByRole('textbox', { name: 'Abstract' })).toHaveValue('We study retrieval.')
  })

  it('saves the corrected metadata', async () => {
    const { api, user, onSaved } = setup()
    const updated = paper({ ...extracted, title: 'Retrieval Helps Language Models Stay Factual' })
    api.on('PATCH', '/api/papers/6', jsonResponse(updated))

    await user.type(screen.getByRole('textbox', { name: 'Title' }), ' Stay Factual  ')
    const authors = screen.getByRole('textbox', { name: /Authors/ })
    await user.clear(authors)
    await user.type(authors, '  Alice Smith {Enter}{Enter}Carol White')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(updated))
    expect(api.callsTo('PATCH', '/api/papers/6')[0].body).toEqual({
      title: 'Retrieval Helps Language Models Stay Factual',
      authors: ['Alice Smith', 'Carol White'],
      year: 2023,
      abstract: 'We study retrieval.',
    })
  })

  it('sends an empty year and abstract as null', async () => {
    const { api, user } = setup()
    api.on('PATCH', '/api/papers/6', jsonResponse(extracted))

    await user.clear(screen.getByRole('spinbutton', { name: 'Year' }))
    await user.clear(screen.getByRole('textbox', { name: 'Abstract' }))
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(api.calls).toHaveLength(1))
    expect(api.calls[0].body).toMatchObject({ year: null, abstract: null })
  })

  it('needs a title', async () => {
    const { api, user } = setup()

    await user.clear(screen.getByRole('textbox', { name: 'Title' }))
    await user.type(screen.getByRole('textbox', { name: 'Title' }), '   ')

    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
    expect(api.calls).toHaveLength(0)
  })

  it('shows why the backend rejected the change', async () => {
    const { api, user, onSaved } = setup()
    api.on('PATCH', '/api/papers/6', errorResponse(404, 'Paper not found.'))

    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByText('Paper not found.')).toBeInTheDocument()
    expect(onSaved).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled()
  })

  it('does not send a year outside 1000 to 2100', async () => {
    const { api, user, onSaved } = setup()
    const year = screen.getByRole('spinbutton', { name: 'Year' })

    await user.clear(year)
    await user.type(year, '3000')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(year).toBeInvalid()
    expect(api.calls).toHaveLength(0)
    expect(onSaved).not.toHaveBeenCalled()
  })

  it('can be cancelled', async () => {
    const { api, user, onCancel } = setup()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onCancel).toHaveBeenCalled()
    expect(api.calls).toHaveLength(0)
  })
})
