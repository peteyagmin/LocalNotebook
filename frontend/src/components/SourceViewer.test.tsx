import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { SourceViewer } from './SourceViewer'
import { mockBackend, source } from '../test/backend'

afterEach(() => vi.unstubAllGlobals())

it('highlights the requested range across the right segment and scrolls to it', async () => {
  const scroll = vi.fn()
  window.HTMLElement.prototype.scrollIntoView = scroll
  mockBackend({
    'GET /notebooks/n1/sources/s1/content': {
      text: 'Alpha beta gamma.\n\nDelta epsilon.',
      segments: [
        { start: 0, end: 17, page: null, heading_path: ['A'] },
        { start: 19, end: 33, page: null, heading_path: ['B'] },
      ],
      page_count: null,
    },
  })
  render(
    <SourceViewer
      notebookId="n1"
      source={source({ guide: null })}
      highlight={{ start: 6, end: 10 }}
      onClose={() => {}}
    />,
  )
  const mark = await screen.findByText('beta')
  expect(mark.tagName).toBe('MARK')
  await waitFor(() => expect(scroll).toHaveBeenCalled())
  expect(screen.queryByText(/^Page /)).not.toBeInTheDocument() // no page markers without pages
})

it('lets the reader pick an earlier capture and says it is not the current one', async () => {
  const content = (text: string) => ({
    text,
    segments: [{ start: 0, end: text.length, page: null, heading_path: null }],
    page_count: null,
  })
  mockBackend({
    'GET /notebooks/n1/sources/s1/content': content('Current text.'),
    'GET /notebooks/n1/sources/s1/versions': [
      { version: 1, fetched_at: '2026-09-01T00:00:00Z', char_count: 10 },
    ],
    'GET /notebooks/n1/sources/s1/versions/1/content': content('Older text.'),
  })
  render(
    <SourceViewer
      notebookId="n1"
      source={source({ type: 'web', version_count: 1, guide: null })}
      onClose={() => {}}
    />,
  )
  expect(await screen.findByText('Current text.')).toBeInTheDocument()
  const picker = await screen.findByRole('combobox', { name: 'Version' })
  await userEvent.selectOptions(picker, '1')
  expect(await screen.findByText('Older text.')).toBeInTheDocument()
  expect(screen.getByText(/This is an earlier capture/)).toBeInTheDocument()
  await userEvent.selectOptions(picker, 'current')
  expect(await screen.findByText('Current text.')).toBeInTheDocument()
  expect(screen.queryByText(/This is an earlier capture/)).not.toBeInTheDocument()
})

it('shows why a refresh failed while the previous capture stays readable', async () => {
  mockBackend({
    'GET /notebooks/n1/sources/s1/content': {
      text: 'Kept text.',
      segments: [{ start: 0, end: 10, page: null, heading_path: null }],
      page_count: null,
    },
  })
  render(
    <SourceViewer
      notebookId="n1"
      source={source({ guide: null, error: 'The refresh failed: the page is gone.' })}
      onClose={() => {}}
    />,
  )
  expect(await screen.findByText('Kept text.')).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('The refresh failed: the page is gone.')
})
