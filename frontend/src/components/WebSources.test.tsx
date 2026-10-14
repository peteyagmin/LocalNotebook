import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { App } from '../App'
import { describeLocation, formatTimestamp } from '../format'
import {
  baseSettings,
  chatMessage,
  mockBackend,
  notebook,
  source,
  type Routes,
} from '../test/backend'

const caps = (over = {}) => ({
  ocr: true,
  stt: { configured: true, installed: true },
  web_import: true,
  discover: { allowed: true, configured: true },
  ...over,
})

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
  'GET /notebooks/n1/sources': [],
  'GET /notebooks/n1/chat': [],
  'GET /notebooks/n1/chat/starters': { questions: [] },
  'GET /notebooks/n1/notes': [],
  'GET /notebooks/n1/artifacts': [],
  'GET /capabilities': caps(),
  ...extra,
})

async function openMenu() {
  await userEvent.click(await screen.findByRole('button', { name: 'Add source' }))
}

// --- helpers -------------------------------------------------------------------------------------

it('formats timestamps and locations', () => {
  expect([0, 65, 754, 3600, 3725].map(formatTimestamp)).toEqual([
    '0:00',
    '1:05',
    '12:34',
    '1:00:00',
    '1:02:05',
  ])
  expect(describeLocation({ start_seconds: 754.4 })).toBe('12:34')
  expect(describeLocation({ page: 3 })).toBe('page 3')
  expect(describeLocation({ heading_path: ['A', 'B'] })).toBe('A › B')
  expect(describeLocation({})).toBe('')
})

// --- the add menu --------------------------------------------------------------------------------

it('explains what is switched off instead of hiding it', async () => {
  mockBackend(
    base({
      'GET /capabilities': caps({
        ocr: false,
        stt: { configured: false, installed: false },
        web_import: false,
        discover: { allowed: false, configured: false },
      }),
    }),
  )
  render(<App />)
  await openMenu()
  const items = Object.fromEntries(
    screen.getAllByRole('menuitem').map((m) => [m.firstChild?.textContent, m]),
  )
  expect(items['Website']).toBeDisabled()
  expect(items['YouTube']).toBeDisabled()
  expect(items['Discover']).toBeDisabled()
  expect(items['Website']).toHaveTextContent('Turned off in Settings (Network).')
  expect(items['Upload files']).toHaveTextContent('Tesseract (not found)')
  expect(items['Upload files']).toHaveTextContent('speech-to-text model')
  expect(items['Upload files']).toBeEnabled()
})

it('sends Discover to Settings with an explanation when no search provider is set', async () => {
  mockBackend(
    base({ 'GET /capabilities': caps({ discover: { allowed: true, configured: false } }) }),
  )
  render(<App />)
  await openMenu()
  expect(screen.getByRole('menuitem', { name: /Discover/ })).toHaveTextContent(
    'Needs a search provider.',
  )
  await userEvent.click(screen.getByRole('menuitem', { name: /Discover/ }))
  expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('Discover needs a search provider')
  expect(window.location.hash).toBe('#/settings?why=discover')
})

// --- importing -----------------------------------------------------------------------------------

it('imports several web addresses, one per line', async () => {
  const calls = mockBackend(base({ 'POST /notebooks/n1/sources/urls': [source({ type: 'web' })] }))
  render(<App />)
  await openMenu()
  await userEvent.click(screen.getByRole('menuitem', { name: 'Website' }))
  const form = screen.getByRole('form', { name: 'Add websites' })
  await userEvent.type(
    within(form).getByLabelText('Web addresses'),
    'https://a.example/1{Enter}https://a.example/2',
  )
  await userEvent.click(within(form).getByRole('button', { name: 'Import' }))
  await waitFor(() =>
    expect(calls.find((c) => c.path.endsWith('/sources/urls'))?.body).toEqual({
      urls: ['https://a.example/1', 'https://a.example/2'],
    }),
  )
  await waitFor(() =>
    expect(screen.queryByRole('form', { name: 'Add websites' })).not.toBeInTheDocument(),
  )
})

it('shows why an address was refused and keeps the form open', async () => {
  mockBackend(
    base({
      'POST /notebooks/n1/sources/urls': () =>
        new Response(
          JSON.stringify({
            error: {
              code: 'unsafe_url',
              message: 'Addresses on this computer or local network are not allowed.',
            },
          }),
          { status: 400 },
        ),
    }),
  )
  render(<App />)
  await openMenu()
  await userEvent.click(screen.getByRole('menuitem', { name: 'Website' }))
  const form = screen.getByRole('form', { name: 'Add websites' })
  await userEvent.type(within(form).getByLabelText('Web addresses'), 'http://192.168.1.1/')
  await userEvent.click(within(form).getByRole('button', { name: 'Import' }))
  expect(await within(form).findByRole('alert')).toHaveTextContent('local network are not allowed')
})

it('imports a YouTube video', async () => {
  const calls = mockBackend(
    base({ 'POST /notebooks/n1/sources/urls': [source({ type: 'youtube' })] }),
  )
  render(<App />)
  await openMenu()
  await userEvent.click(screen.getByRole('menuitem', { name: 'YouTube' }))
  await userEvent.type(screen.getByLabelText('YouTube address'), 'https://youtu.be/dQw4w9WgXcQ')
  await userEvent.click(screen.getByRole('button', { name: 'Import' }))
  await waitFor(() =>
    expect(calls.find((c) => c.path.endsWith('/sources/urls'))?.body).toEqual({
      urls: ['https://youtu.be/dQw4w9WgXcQ'],
    }),
  )
})

// --- Discover ------------------------------------------------------------------------------------

const suggestions = [
  {
    title: 'Harbor history',
    url: 'https://a.example/h',
    note: 'Covers the founding.',
    kind: 'web',
  },
  {
    title: 'Harbor talk',
    url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
    note: 'A lecture.',
    kind: 'youtube',
  },
  { title: 'Tides', url: 'https://b.example/t', note: 'Explains tides.', kind: 'web' },
]

it('suggests sources, imports only the ticked ones, and imports nothing automatically', async () => {
  const calls = mockBackend(
    base({
      'POST /notebooks/n1/discover': { suggestions },
      'POST /notebooks/n1/sources/urls': [
        source({ type: 'web' }),
        source({ id: 's2', type: 'youtube' }),
      ],
    }),
  )
  render(<App />)
  await openMenu()
  await userEvent.click(screen.getByRole('menuitem', { name: /Discover/ }))
  const dialog = screen.getByRole('region', { name: 'Discover sources' })
  await userEvent.type(within(dialog).getByLabelText('Topic'), 'harbors')
  await userEvent.click(within(dialog).getByRole('button', { name: 'Search' }))
  expect(await within(dialog).findByText('Covers the founding.')).toBeInTheDocument()
  expect(within(dialog).getByRole('link', { name: 'https://a.example/h' })).toHaveAttribute(
    'href',
    'https://a.example/h',
  )
  expect(calls.find((c) => c.path.endsWith('/discover'))?.body).toEqual({ topic: 'harbors' })
  expect(calls.some((c) => c.path.endsWith('/sources/urls'))).toBe(false) // nothing imported yet
  expect(within(dialog).getByRole('button', { name: 'Import selected (0)' })).toBeDisabled()

  await userEvent.click(within(dialog).getByRole('checkbox', { name: 'Import Harbor history' }))
  await userEvent.click(within(dialog).getByRole('checkbox', { name: 'Import Harbor talk' }))
  await userEvent.click(within(dialog).getByRole('button', { name: 'Import selected (2)' }))
  await waitFor(() =>
    expect(calls.find((c) => c.path.endsWith('/sources/urls'))?.body).toEqual({
      urls: ['https://a.example/h', 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'],
    }),
  )
})

it('says so when Discover finds nothing readable and reports errors', async () => {
  let answer: Response | { suggestions: unknown[] } = { suggestions: [] }
  mockBackend(base({ 'POST /notebooks/n1/discover': () => answer }))
  render(<App />)
  await openMenu()
  await userEvent.click(screen.getByRole('menuitem', { name: /Discover/ }))
  const dialog = screen.getByRole('region', { name: 'Discover sources' })
  await userEvent.type(within(dialog).getByLabelText('Topic'), 'nothing')
  await userEvent.click(within(dialog).getByRole('button', { name: 'Search' }))
  expect(await within(dialog).findByText(/No readable results/)).toBeInTheDocument()
  answer = new Response(
    JSON.stringify({
      error: { code: 'search_failed', message: 'Could not get results from the search provider.' },
    }),
    { status: 502 },
  )
  await userEvent.click(within(dialog).getByRole('button', { name: 'Search' }))
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('search provider')
})

// --- source rows and the viewer --------------------------------------------------------------------

it('shows web and video sources with their origin, capture date, and a refresh action', async () => {
  const calls = mockBackend(
    base({
      'GET /notebooks/n1/sources': [
        source({
          id: 'w',
          name: 'Harbor page',
          type: 'web',
          url: 'https://a.example/harbor',
          fetched_at: '2026-10-01T10:00:00Z',
          version_count: 2,
        }),
        source({
          id: 'v',
          name: 'Harbor talk',
          type: 'youtube',
          url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
          fetched_at: '2026-10-02T10:00:00Z',
        }),
        source({ id: 'p', name: 'Doc.pdf' }),
      ],
      'POST /notebooks/n1/sources/w/refresh': source({ id: 'w', type: 'web', state: 'queued' }),
    }),
  )
  render(<App />)
  const web = (await screen.findByRole('checkbox', { name: 'Use Harbor page' })).closest('li')!
  expect(within(web).getByText('Web')).toBeInTheDocument()
  expect(within(web).getByRole('link', { name: 'https://a.example/harbor' })).toHaveAttribute(
    'href',
    'https://a.example/harbor',
  )
  expect(within(web).getByText(/Captured Oct 1, 2026/)).toBeInTheDocument()
  expect(within(web).getByText(/2 earlier versions/)).toBeInTheDocument()
  const video = screen.getByRole('checkbox', { name: 'Use Harbor talk' }).closest('li')!
  expect(within(video).getByText('Video')).toBeInTheDocument()
  expect(within(video).queryByRole('button', { name: /Refresh/ })).not.toBeInTheDocument()
  const pdf = screen.getByRole('checkbox', { name: 'Use Doc.pdf' }).closest('li')!
  expect(within(pdf).queryByRole('link')).not.toBeInTheDocument()
  await userEvent.click(within(web).getByRole('button', { name: 'Refresh Harbor page from web' }))
  await waitFor(() => expect(calls.some((c) => c.path.endsWith('/w/refresh'))).toBe(true))
})

const videoContent = {
  text: 'Welcome to the harbor.\n\nShips arrive daily.',
  segments: [
    { start: 0, end: 22, page: null, heading_path: null, start_s: 0, end_s: 29 },
    { start: 24, end: 43, page: null, heading_path: null, start_s: 754, end_s: 790 },
  ],
  page_count: null,
}

it('shows video transcripts with clickable timestamps and an open-at-this-time link for cited passages', async () => {
  mockBackend(
    base({
      'GET /notebooks/n1/sources': [
        source({
          id: 'v',
          name: 'Harbor talk',
          type: 'youtube',
          url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
          meta: { video_id: 'dQw4w9WgXcQ', channel: 'Harbor Channel' },
        }),
      ],
      'GET /notebooks/n1/sources/v/content': videoContent,
      'GET /notebooks/n1/chat': [
        chatMessage({
          citations: [
            {
              ...chatMessage().citations[0],
              source_id: 'v',
              source_name: 'Harbor talk',
              location: {
                page: null,
                heading_path: null,
                char_start: 24,
                char_end: 43,
                start_seconds: 754,
                end_seconds: 790,
              },
            },
          ],
        }),
      ],
    }),
  )
  render(<App />)
  const chip = await screen.findByRole('button', { name: 'Citation 1: Harbor talk' })
  expect(within(chip.parentElement!).getByRole('tooltip')).toHaveTextContent('12:34') // timestamp in the hover text
  await userEvent.click(chip)
  const viewer = await screen.findByRole('dialog', { name: 'Source: Harbor talk' })
  const open = await within(viewer).findByRole('link', {
    name: /Open in browser at this time \(12:34\)/,
  })
  expect(open).toHaveAttribute('href', 'https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=754s')
  expect(within(viewer).getByRole('link', { name: '0:00' })).toHaveAttribute(
    'href',
    expect.stringMatching(/&t=0s$/),
  )
  expect(within(viewer).getByText(/Harbor Channel/)).toBeInTheDocument()
})

it('shows audio timestamps as plain markers', async () => {
  mockBackend(
    base({
      'GET /notebooks/n1/sources': [source({ id: 'a', name: 'Talk.mp3', type: 'audio' })],
      'GET /notebooks/n1/sources/a/content': videoContent,
    }),
  )
  render(<App />)
  await userEvent.click(await screen.findByRole('button', { name: 'Talk.mp3' }))
  const viewer = await screen.findByRole('dialog', { name: 'Source: Talk.mp3' })
  expect(await within(viewer).findByText('12:34')).toBeInTheDocument()
  expect(within(viewer).queryByRole('link', { name: '12:34' })).not.toBeInTheDocument()
})

// --- settings ------------------------------------------------------------------------------------

it('lets you switch the network features off and states the terms-of-service responsibility', async () => {
  const calls = mockBackend({
    'GET /settings': baseSettings,
    'GET /notebooks': [],
    'GET /speech/stt': {
      model: '',
      configured: false,
      installed: false,
      downloads_allowed: true,
      state: 'idle',
    },
    'PUT /settings': (b: unknown) => ({ ...baseSettings, ...(b as object) }),
  })
  window.location.hash = '#/settings'
  render(<App />)
  const network = await screen.findByRole('region', { name: 'Network' })
  expect(within(network).getByLabelText(/Import web pages and videos/)).toBeChecked()
  await userEvent.click(within(network).getByLabelText(/Import web pages and videos/))
  await userEvent.type(
    within(network).getByLabelText(/Search provider address/),
    'http://localhost:8888',
  )
  const speech = screen.getByRole('region', { name: 'Speech to text' })
  const transcribe = within(speech).getByLabelText(/Transcribe videos without captions/)
  expect(transcribe).not.toBeChecked() // off by default
  expect(speech).toHaveTextContent('responsible for complying with the platform’s terms of service')
  await userEvent.click(transcribe)
  await userEvent.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => {
    const body = calls.find((c) => c.method === 'PUT')?.body as Record<string, unknown>
    expect(body).toMatchObject({
      allow_web_import: false,
      searxng_url: 'http://localhost:8888',
      transcribe_uncaptioned_videos: true,
    })
  })
})

it('downloads the speech model only after confirmation and shows progress', async () => {
  let polls = 0
  const calls = mockBackend({
    'GET /settings': { ...baseSettings, stt_model: 'tiny' },
    'GET /notebooks': [],
    'GET /speech/stt': () => {
      polls += 1
      return polls <= 1
        ? {
            model: 'tiny',
            configured: true,
            installed: false,
            downloads_allowed: true,
            state: 'idle',
          }
        : {
            model: 'tiny',
            configured: true,
            installed: false,
            downloads_allowed: true,
            state: 'downloading',
            progress: 0.5,
          }
    },
    'POST /speech/stt/download': {
      model: 'tiny',
      configured: true,
      installed: false,
      downloads_allowed: true,
      state: 'downloading',
      progress: 0,
    },
  })
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  window.location.hash = '#/settings'
  render(<App />)
  const button = await screen.findByRole('button', { name: 'Download model' })
  await userEvent.click(button)
  expect(confirm).toHaveBeenCalledWith(expect.stringContaining('"tiny"'))
  expect(calls.some((c) => c.method === 'POST')).toBe(false) // declined: nothing downloaded
  confirm.mockReturnValue(true)
  await userEvent.click(screen.getByRole('button', { name: 'Download model' }))
  await waitFor(() =>
    expect(calls.find((c) => c.path === '/speech/stt/download')?.body).toEqual({ confirm: true }),
  )
  expect(await screen.findByRole('progressbar', { name: 'Downloading model' })).toBeInTheDocument()
})

it('explains why the model cannot be downloaded when downloads are off, and shows when it is installed', async () => {
  mockBackend({
    'GET /settings': { ...baseSettings, stt_model: 'tiny' },
    'GET /notebooks': [],
    'GET /speech/stt': {
      model: 'tiny',
      configured: true,
      installed: false,
      downloads_allowed: false,
      state: 'idle',
    },
  })
  window.location.hash = '#/settings'
  const { unmount } = render(<App />)
  expect(await screen.findByRole('button', { name: 'Download model' })).toBeDisabled()
  expect(screen.getByText(/Model downloads are turned off/)).toBeInTheDocument()
  unmount()
  mockBackend({
    'GET /settings': { ...baseSettings, stt_model: 'tiny' },
    'GET /notebooks': [],
    'GET /speech/stt': {
      model: 'tiny',
      configured: true,
      installed: true,
      downloads_allowed: true,
      state: 'idle',
    },
  })
  render(<App />)
  expect(await screen.findByText(/is installed/)).toBeInTheDocument()
})
