import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App, remoteHost } from './App'
import { baseSettings, mockBackend, notebook, source } from './test/backend'

beforeEach(() => {
  window.location.hash = ''
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('remoteHost', () => {
  it('is null for loopback and set otherwise', () => {
    expect(remoteHost('http://127.0.0.1:11434/v1')).toBeNull()
    expect(remoteHost('http://localhost:11434/v1')).toBeNull()
    expect(remoteHost('http://[::1]:11434/v1')).toBeNull()
    expect(remoteHost('https://api.example.com/v1')).toBe('api.example.com')
  })
})

describe('shell', () => {
  it('warns when the model server is not loopback', async () => {
    mockBackend({
      'GET /settings': { ...baseSettings, llm_base_url: 'https://api.example.com/v1' },
      'GET /notebooks': [],
    })
    render(<App />)
    expect(
      await screen.findByText('AI requests are being sent to api.example.com.'),
    ).toBeInTheDocument()
  })

  it('shows the setup wizard checks before setup is completed', async () => {
    mockBackend({
      'GET /settings': { ...baseSettings, setup_completed: false },
      'GET /setup/checks': {
        checks: [
          {
            id: 'ffmpeg',
            label: 'ffmpeg installed',
            ok: false,
            detail: 'Not found',
            fix: 'Install it',
          },
        ],
      },
    })
    render(<App />)
    expect(await screen.findByText('ffmpeg installed')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Install it')).toBeInTheDocument())
  })
})

describe('home', () => {
  it('lists notebooks with metadata', async () => {
    mockBackend({ 'GET /settings': baseSettings, 'GET /notebooks': [notebook()] })
    render(<App />)
    expect(await screen.findByRole('link', { name: 'My notebook' })).toHaveAttribute(
      'href',
      '#/notebooks/n1',
    )
    expect(screen.getByText(/2 sources · 2.0 KB/)).toBeInTheDocument()
  })

  it('creates a notebook and opens it', async () => {
    const calls = mockBackend({
      'GET /settings': baseSettings,
      'GET /notebooks': [],
      'POST /notebooks': notebook({ id: 'new1' }),
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'New notebook' }))
    await userEvent.type(screen.getByLabelText('Notebook name'), 'Fresh')
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(window.location.hash).toBe('#/notebooks/new1'))
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ name: 'Fresh' })
  })

  it('asks for confirmation before deleting, and respects "cancel"', async () => {
    const calls = mockBackend({
      'GET /settings': baseSettings,
      'GET /notebooks': [notebook()],
      'DELETE /notebooks/:id': undefined,
    })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Delete My notebook' }))
    expect(confirm).toHaveBeenCalled()
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
    confirm.mockReturnValue(true)
    await userEvent.click(screen.getByRole('button', { name: 'Delete My notebook' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true))
  })

  it('renames and duplicates', async () => {
    const calls = mockBackend({
      'GET /settings': baseSettings,
      'GET /notebooks': [notebook()],
      'PATCH /notebooks/:id': notebook({ name: 'Renamed' }),
      'POST /notebooks/:id/duplicate': notebook({ id: 'n2' }),
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Duplicate My notebook' }))
    await waitFor(() => expect(calls.some((c) => c.path === '/notebooks/n1/duplicate')).toBe(true))
    await userEvent.click(screen.getByRole('button', { name: 'Rename My notebook' }))
    const input = screen.getByLabelText('New name')
    await userEvent.clear(input)
    await userEvent.type(input, 'Renamed')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ name: 'Renamed' }),
    )
  })
})

describe('notebook workspace', () => {
  function open(sources = [source()], extra = {}) {
    window.location.hash = '#/notebooks/n1'
    return mockBackend({
      'GET /settings': baseSettings,
      'GET /notebooks/n1': notebook(),
      'GET /notebooks/n1/sources': sources,
      'GET /notebooks/n1/chat': [],
      'GET /notebooks/n1/chat/starters': { questions: [] },
      ...extra,
    })
  }

  it('shows the three panes and can collapse one', async () => {
    open()
    render(<App />)
    for (const name of ['Sources', 'Chat', 'Studio']) {
      expect(await screen.findByRole('region', { name })).toBeInTheDocument()
    }
    await userEvent.click(screen.getByRole('button', { name: 'Collapse Sources pane' }))
    expect(screen.getByRole('button', { name: 'Expand Sources pane' })).toBeInTheDocument()
  })

  it('shows state, progress and failure with Retry', async () => {
    const calls = open(
      [
        source({
          id: 'a',
          name: 'Busy.txt',
          state: 'processing',
          progress: 0.5,
          stage: 'Indexing',
        }),
        source({ id: 'b', name: 'Bad.pdf', state: 'failed', error: 'No readable text was found.' }),
      ],
      { 'POST /notebooks/n1/sources/b/retry': source({ id: 'b', state: 'queued' }) },
    )
    render(<App />)
    expect(await screen.findByText('Indexing')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Processing Busy.txt' })).toHaveAttribute(
      'value',
      '0.5',
    )
    expect(screen.getByText('No readable text was found.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.path.endsWith('/b/retry'))).toBe(true),
    )
  })

  it('toggles a source and selects all / none', async () => {
    const calls = open([source()], {
      'PATCH /notebooks/n1/sources/s1': source({ enabled: false }),
      'POST /notebooks/n1/sources/enabled': [source({ enabled: false })],
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('checkbox', { name: 'Use Doc.pdf' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ enabled: false }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Select none' }))
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith('/sources/enabled'))?.body).toEqual({
        enabled: false,
      }),
    )
  })

  it('uploads files and pastes text', async () => {
    const calls = open([], {
      'POST /notebooks/n1/sources/files': [],
      'POST /notebooks/n1/sources/text': [],
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Add source' }))
    expect(screen.getAllByRole('menuitem').map((m) => m.textContent)).toEqual([
      'Upload files',
      'Paste text',
    ])
    await userEvent.upload(
      screen.getByLabelText('Choose files'),
      new File(['hello'], 'a.txt', { type: 'text/plain' }),
    )
    await waitFor(() => expect(calls.some((c) => c.path.endsWith('/sources/files'))).toBe(true))
    expect(calls.find((c) => c.path.endsWith('/sources/files'))?.body).toBeInstanceOf(FormData)

    await userEvent.click(screen.getByRole('menuitem', { name: 'Paste text' }))
    const form = screen.getByRole('form', { name: 'Paste text' })
    await userEvent.type(within(form).getByLabelText('Text'), 'Some words')
    await userEvent.click(within(form).getByRole('button', { name: 'Add' }))
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith('/sources/text'))?.body).toEqual({
        name: '',
        text: 'Some words',
      }),
    )
  })

  it('confirms before removing a source', async () => {
    const calls = open([source()], { 'DELETE /notebooks/n1/sources/s1': undefined })
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Remove Doc.pdf' }))
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
  })

  it('opens the viewer with guide and page markers; Esc closes it', async () => {
    open([source()], {
      'GET /notebooks/n1/sources/s1/content': {
        text: 'Page one text.\n\nPage two text.',
        segments: [
          { start: 0, end: 14, page: 1, heading_path: null },
          { start: 16, end: 30, page: 2, heading_path: null },
        ],
        page_count: 2,
      },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Doc.pdf' }))
    const viewer = await screen.findByRole('dialog', { name: 'Source: Doc.pdf' })
    expect(within(viewer).getByText('A guide summary.')).toBeInTheDocument()
    expect(within(viewer).getByText('alpha')).toBeInTheDocument()
    expect(await within(viewer).findByText('Page 1')).toBeInTheDocument()
    expect(within(viewer).getByText('Page 2')).toBeInTheDocument()
    expect(within(viewer).getByText('Page two text.')).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })
})
