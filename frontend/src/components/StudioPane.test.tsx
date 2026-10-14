import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { App } from '../App'
import {
  artifact,
  artifactDetail,
  baseSettings,
  chatMessage,
  mockBackend,
  note,
  notebook,
  source,
  sseResponse,
  type Routes,
} from '../test/backend'

beforeEach(() => {
  window.location.hash = '#/notebooks/n1'
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

const base = (extra: Routes = {}): Routes => ({
  'GET /settings': baseSettings,
  'GET /notebooks/n1': notebook(),
  'GET /notebooks/n1/sources': [source()],
  'GET /notebooks/n1/chat': [],
  'GET /notebooks/n1/chat/starters': { questions: [] },
  'GET /notebooks/n1/notes': [],
  'GET /notebooks/n1/artifacts': [],
  ...extra,
})

const studio = () => screen.findByRole('region', { name: 'Studio' })

it('offers one button per artifact type and starts a generation with the focus', async () => {
  const calls = mockBackend(
    base({
      'POST /notebooks/n1/artifacts': artifactDetail({
        state: 'queued',
        has_content: false,
        content: '',
        citations: [],
      }),
      'GET /notebooks/n1/artifacts/a1': artifactDetail(),
    }),
  )
  render(<App />)
  const pane = await studio()
  const create = within(pane).getByRole('region', { name: 'Create' })
  expect(
    within(create)
      .getAllByRole('button')
      .map((b) => b.textContent),
  ).toEqual([
    'Summary',
    'Briefing',
    'Study guide',
    'FAQ',
    'Timeline',
    'Mind map',
    'Flashcards & quiz',
  ])
  await userEvent.type(within(pane).getByLabelText('Focus (optional)'), 'for beginners')
  await userEvent.click(within(pane).getByRole('button', { name: 'Study guide' }))
  await waitFor(() =>
    expect(
      calls.find((c) => c.method === 'POST' && c.path === '/notebooks/n1/artifacts')?.body,
    ).toEqual({
      kind: 'study_guide',
      focus: 'for beginners',
    }),
  )
  expect(
    await screen.findByRole('region', { name: 'Artifact: Notebook summary' }),
  ).toBeInTheDocument()
})

it('lists artifacts with progress and Cancel, failure with Retry, and the stale badge', async () => {
  const calls = mockBackend(
    base({
      'GET /notebooks/n1/artifacts': [
        artifact({
          id: 'r',
          title: 'Briefing document',
          state: 'running',
          progress: 0.4,
          stage: 'Reading part 1 of 3',
        }),
        artifact({
          id: 'f',
          title: 'FAQ',
          state: 'failed',
          error: 'No enabled sources.',
          has_content: false,
        }),
        artifact({ id: 's', title: 'Study guide', stale: true }),
      ],
      'POST /notebooks/n1/artifacts/r/cancel': undefined,
      'POST /notebooks/n1/artifacts/f/regenerate': artifactDetail(),
      'POST /notebooks/n1/artifacts/s/regenerate': artifactDetail(),
    }),
  )
  render(<App />)
  expect(await screen.findByText('Reading part 1 of 3')).toBeInTheDocument()
  expect(screen.getByRole('progressbar', { name: 'Generating Briefing document' })).toHaveAttribute(
    'value',
    '0.4',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  await waitFor(() => expect(calls.some((c) => c.path.endsWith('/r/cancel'))).toBe(true))
  expect(screen.getByText('No enabled sources.')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
  await waitFor(() => expect(calls.some((c) => c.path.endsWith('/f/regenerate'))).toBe(true))
  await userEvent.click(screen.getByRole('button', { name: 'Sources changed — regenerate?' }))
  await waitFor(() => expect(calls.some((c) => c.path.endsWith('/s/regenerate'))).toBe(true))
})

it('confirms before deleting an artifact', async () => {
  const calls = mockBackend(
    base({
      'GET /notebooks/n1/artifacts': [artifact()],
      'DELETE /notebooks/n1/artifacts/a1': undefined,
    }),
  )
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  render(<App />)
  await userEvent.click(await screen.findByRole('button', { name: 'Delete Notebook summary' }))
  expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
  confirm.mockReturnValue(true)
  await userEvent.click(screen.getByRole('button', { name: 'Delete Notebook summary' }))
  await waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true))
})

it('shows an artifact with citation chips, the stale banner, expand, and exports in three formats', async () => {
  const created: string[] = []
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: vi.fn(() => 'blob:x'),
    revokeObjectURL: vi.fn(),
  })
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    created.push(this.download)
  })
  mockBackend(
    base({
      'GET /notebooks/n1/artifacts': [artifact({ stale: true })],
      'GET /notebooks/n1/artifacts/a1': artifactDetail({ stale: true }),
      'GET /notebooks/n1/artifacts/a1/export': () =>
        new Response('file', {
          headers: { 'Content-Disposition': 'attachment; filename="Notebook-summary.pdf"' },
        }),
    }),
  )
  render(<App />)
  await userEvent.click(await screen.findByRole('button', { name: 'Notebook summary' }))
  const view = await screen.findByRole('region', { name: 'Artifact: Notebook summary' })
  expect(within(view).getByRole('heading', { name: 'Key points' })).toBeInTheDocument()
  expect(within(view).getByRole('button', { name: 'Citation 1: Doc.pdf' })).toBeInTheDocument()
  expect(within(view).getByRole('status')).toHaveTextContent('Sources changed — regenerate?')

  await userEvent.click(within(view).getByRole('button', { name: 'Export' }))
  expect(
    within(view)
      .getAllByRole('menuitem')
      .map((m) => m.textContent),
  ).toEqual(['Markdown (.md)', 'Word (.docx)', 'PDF (.pdf)'])
  await userEvent.click(within(view).getByRole('menuitem', { name: 'PDF (.pdf)' }))
  await waitFor(() => expect(created).toEqual(['Notebook-summary.pdf']))
  click.mockRestore()

  const expand = within(view).getByRole('button', { name: 'Expand' })
  await userEvent.click(expand)
  expect(within(view).getByRole('button', { name: 'Shrink' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
})

it('creates a note, edits it with a live preview, and saves automatically', async () => {
  const calls = mockBackend(
    base({
      'POST /notebooks/n1/notes': note({
        id: 'n-1',
        title: 'Untitled note',
        content: '',
        citations: [],
      }),
      'GET /notebooks/n1/notes/n-1': note({ title: 'Untitled note', content: '', citations: [] }),
      'PATCH /notebooks/n1/notes/n-1': note({ citations: [] }),
    }),
  )
  render(<App />)
  await userEvent.click(await screen.findByRole('button', { name: 'New note' }))
  const editor = await screen.findByRole('region', { name: 'Note editor' })
  await userEvent.type(within(editor).getByLabelText('Note content'), 'Hello **bold**')
  expect(await within(editor).findByText('bold', { selector: 'strong' })).toBeInTheDocument() // live preview
  await waitFor(
    () => {
      const patch = calls.filter((c) => c.method === 'PATCH').at(-1)
      expect(patch?.body).toEqual({ title: 'Untitled note', content: 'Hello **bold**' })
    },
    { timeout: 3000 },
  )
  expect(await within(editor).findByText('Saved')).toBeInTheDocument()
})

it('runs Summarize, Combine and Convert on selected notes', async () => {
  const calls = mockBackend(
    base({
      'GET /notebooks/n1/notes': [
        { id: 'x', title: 'First', preview: 'one', updated_at: 't' },
        { id: 'y', title: 'Second', preview: 'two', updated_at: 't' },
      ],
      'POST /notebooks/n1/notes/summarize': note({ id: 'n-s', title: 'Summary of 2 notes' }),
      'POST /notebooks/n1/notes/combine': note({ id: 'n-c', title: 'Combined notes' }),
      'POST /notebooks/n1/notes/convert-to-source': [source({ id: 'a' }), source({ id: 'b' })],
      'GET /notebooks/n1/notes/n-s': note({ id: 'n-s', title: 'Summary of 2 notes' }),
      'GET /notebooks/n1/notes/n-c': note({ id: 'n-c', title: 'Combined notes' }),
    }),
  )
  render(<App />)
  expect(
    screen.queryByRole('group', { name: 'Actions for selected notes' }),
  ).not.toBeInTheDocument()
  await userEvent.click(await screen.findByRole('checkbox', { name: 'Select note First' }))
  await userEvent.click(screen.getByRole('checkbox', { name: 'Select note Second' }))
  const actions = screen.getByRole('group', { name: 'Actions for selected notes' })

  await userEvent.click(within(actions).getByRole('button', { name: 'Convert to source' }))
  expect(await screen.findByText('Added 2 sources.')).toBeInTheDocument()
  expect(calls.find((c) => c.path.endsWith('/convert-to-source'))?.body).toEqual({
    note_ids: ['x', 'y'],
  })

  await userEvent.click(within(actions).getByRole('button', { name: 'Summarize' }))
  expect(await screen.findByDisplayValue('Summary of 2 notes')).toBeInTheDocument()
  expect(calls.find((c) => c.path.endsWith('/notes/summarize'))?.body).toEqual({
    note_ids: ['x', 'y'],
  })
})

it('combines notes and opens the result', async () => {
  const calls = mockBackend(
    base({
      'GET /notebooks/n1/notes': [
        { id: 'x', title: 'First', preview: '', updated_at: 't' },
        { id: 'y', title: 'Second', preview: '', updated_at: 't' },
      ],
      'POST /notebooks/n1/notes/combine': note({ id: 'n-c', title: 'Combined notes' }),
      'GET /notebooks/n1/notes/n-c': note({ id: 'n-c', title: 'Combined notes' }),
    }),
  )
  render(<App />)
  await userEvent.click(await screen.findByRole('checkbox', { name: 'Select note First' }))
  await userEvent.click(screen.getByRole('checkbox', { name: 'Select note Second' }))
  await userEvent.click(screen.getByRole('button', { name: 'Combine into one note' }))
  expect(await screen.findByDisplayValue('Combined notes')).toBeInTheDocument()
  expect(calls.find((c) => c.path.endsWith('/combine'))?.body).toEqual({ note_ids: ['x', 'y'] })
})

it('saves a chat answer to a note and opens it', async () => {
  const calls = mockBackend(
    base({
      'GET /notebooks/n1/chat': [chatMessage({ id: 'm9' })],
      'POST /notebooks/n1/chat/messages/m9/save-note': note({
        id: 'n-1',
        title: 'What do zebras eat?',
      }),
      'GET /notebooks/n1/notes/n-1': note({ id: 'n-1', title: 'What do zebras eat?' }),
    }),
  )
  render(<App />)
  await userEvent.click(await screen.findByRole('button', { name: 'Save to note' }))
  await waitFor(() => expect(calls.some((c) => c.path.endsWith('/m9/save-note'))).toBe(true))
  expect(await screen.findByDisplayValue('What do zebras eat?')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Saved to notes' })).toBeDisabled()
})

it('opens a note from a search result', async () => {
  mockBackend(
    base({
      'GET /notebooks/n1/search': [
        {
          kind: 'note',
          note_id: 'n-1',
          chunk_id: 'nc1',
          source_id: null,
          source_name: 'My note',
          location: { page: null, heading_path: null, char_start: 0, char_end: 0 },
          excerpt: 'okapi habitat',
          char_start: 0,
          char_end: 0,
        },
      ],
      'GET /notebooks/n1/notes/n-1': note(),
    }),
  )
  render(<App />)
  await userEvent.type(await screen.findByLabelText('Search sources'), 'okapi')
  const results = await screen.findByRole('region', { name: 'Search results' })
  expect(within(results).getByText('Note')).toBeInTheDocument()
  await userEvent.click(within(results).getByRole('button', { name: /My note/ }))
  expect(await screen.findByRole('region', { name: 'Note editor' })).toBeInTheDocument()
})

it('uses the sse helper without breaking (sanity)', () => {
  expect(sseResponse([]).status).toBe(200)
})
