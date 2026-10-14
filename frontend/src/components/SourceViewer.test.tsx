import { render, screen } from '@testing-library/react'
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
  expect(scroll).toHaveBeenCalled()
  expect(screen.queryByText(/^Page /)).not.toBeInTheDocument() // no page markers without pages
})
