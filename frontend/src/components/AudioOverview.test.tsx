import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { App } from '../App'
import type { AudioTranscript, AudioTurn } from '../api'
import {
  artifact,
  artifactDetail,
  baseSettings,
  mockBackend,
  notebook,
  source,
  type Routes,
} from '../test/backend'

const turns: AudioTurn[] = [
  { speaker: 'A', text: 'Welcome to the show.', chunk_ids: [], start: 0, end: 10 },
  { speaker: 'B', text: 'Zebras graze on grass.', chunk_ids: ['c1'], start: 10.4, end: 30 },
  { speaker: 'A', text: 'Closing words.', chunk_ids: [], start: 30.5, end: 40 },
]
const transcript = (over = {}): AudioTranscript => ({
  title: 'Zebra talk',
  options: { length: 'default', format: 'deep_dive' },
  turns,
  duration: 40,
  outdated: false,
  ...over,
})
const audioArtifact = artifact({
  id: 'au',
  kind: 'audio_overview',
  title: 'Zebra talk',
  options: { length: 'default', format: 'deep_dive' },
})
const audioDetail = (over = {}) =>
  artifactDetail({
    ...audioArtifact,
    format: 'audio',
    content: undefined,
    data: transcript(),
    ...over,
  })

const caps = (over = {}) => ({
  ocr: true,
  audio_overview: { ready: true, problems: [] },
  stt: { configured: true, installed: true },
  web_import: true,
  discover: { allowed: true, configured: true },
  ...over,
})

const base = (extra: Routes = {}): Routes => ({
  'GET /settings': baseSettings,
  'GET /notebooks/n1': notebook(),
  'GET /notebooks/n1/sources': [source()],
  'GET /notebooks/n1/chat': [],
  'GET /notebooks/n1/chat/starters': { questions: [] },
  'GET /notebooks/n1/notes': [],
  'GET /notebooks/n1/artifacts': [audioArtifact],
  'GET /notebooks/n1/artifacts/au': audioDetail(),
  'GET /notebooks/n1/artifacts/au/audio': () => new Response('mp3bytes'),
  'GET /capabilities': caps(),
  ...extra,
})

let play: ReturnType<typeof vi.fn>
let pause: ReturnType<typeof vi.fn>

beforeEach(() => {
  window.location.hash = '#/notebooks/n1'
  play = vi.fn(async () => {})
  pause = vi.fn()
  window.HTMLMediaElement.prototype.play = play as never
  window.HTMLMediaElement.prototype.pause = pause as never
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: vi.fn(() => 'blob:audio'),
    revokeObjectURL: vi.fn(),
  })
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

async function openAudio() {
  render(<App />)
  await userEvent.click(await screen.findByRole('button', { name: 'Zebra talk' }))
  const view = await screen.findByRole('region', { name: 'Artifact: Zebra talk' })
  const player = await within(view).findByRole('group', { name: 'Audio player' })
  await waitFor(() => expect(within(player).getByRole('button', { name: 'Play' })).toBeEnabled())
  return { view, player, audio: player.querySelector('audio') as HTMLAudioElement }
}

it('plays, pauses, skips 15 seconds, seeks and changes speed', async () => {
  mockBackend(base())
  const { player, audio } = await openAudio()
  expect(audio).toHaveAttribute('src', 'blob:audio')

  await userEvent.click(within(player).getByRole('button', { name: 'Play' }))
  expect(play).toHaveBeenCalled()
  fireEvent.play(audio)
  await userEvent.click(await within(player).findByRole('button', { name: 'Pause' }))
  expect(pause).toHaveBeenCalled()

  await userEvent.click(within(player).getByRole('button', { name: 'Forward 15 seconds' }))
  expect(audio.currentTime).toBe(15)
  await userEvent.click(within(player).getByRole('button', { name: 'Back 15 seconds' }))
  expect(audio.currentTime).toBe(0)
  await userEvent.click(within(player).getByRole('button', { name: 'Back 15 seconds' }))
  expect(audio.currentTime).toBe(0) // not below zero

  fireEvent.change(within(player).getByRole('slider', { name: 'Seek' }), {
    target: { value: '25' },
  })
  expect(audio.currentTime).toBe(25)

  const speed = within(player).getByRole('combobox', { name: 'Speed' })
  expect(
    within(speed)
      .getAllByRole('option')
      .map((o) => o.textContent),
  ).toEqual(['0.75×', '1×', '1.25×', '1.5×', '1.75×', '2×'])
  await userEvent.selectOptions(speed, '2')
  expect(audio.playbackRate).toBe(2)
})

it('highlights the current turn and jumps to a turn when it is clicked', async () => {
  mockBackend(base())
  const { view, audio } = await openAudio()
  const items = within(within(view).getByRole('region', { name: 'Transcript' })).getAllByRole(
    'listitem',
  )
  expect(items.filter((i) => i.getAttribute('aria-current') === 'true')).toHaveLength(1)

  audio.currentTime = 12
  fireEvent.timeUpdate(audio)
  await waitFor(() => expect(items[1]).toHaveAttribute('aria-current', 'true'))
  expect(items[0]).not.toHaveAttribute('aria-current')

  await userEvent.click(within(items[2]).getByRole('button', { name: /Play from 0:30/ }))
  expect(audio.currentTime).toBe(30.5)
  expect(play).toHaveBeenCalled()
  await waitFor(() => expect(items[2]).toHaveAttribute('aria-current', 'true'))
  expect(within(items[1]).getByRole('button', { name: 'Citation 1: Doc.pdf' })).toBeInTheDocument()
})

it('edits the script (text, speaker, order, delete), saves it, and re-synthesizes', async () => {
  let saved: unknown = null
  const calls = mockBackend(
    base({
      'PUT /notebooks/n1/artifacts/au/script': (body: unknown) => {
        saved = body
        return audioDetail({ data: transcript({ outdated: true }) })
      },
      'POST /notebooks/n1/artifacts/au/resynthesize': audioDetail(),
    }),
  )
  const { view } = await openAudio()
  await userEvent.click(within(view).getByRole('button', { name: 'Edit script' }))
  const editor = await within(view).findByRole('region', { name: 'Script editor' })

  const text = within(editor).getByRole('textbox', { name: 'Text of turn 1' })
  await userEvent.clear(text)
  await userEvent.type(text, 'Hello everyone.')
  await userEvent.selectOptions(
    within(editor).getByRole('combobox', { name: 'Speaker for turn 1' }),
    'B',
  )
  await userEvent.click(within(editor).getByRole('button', { name: 'Move turn 3 up' }))
  await userEvent.click(within(editor).getByRole('button', { name: 'Delete turn 1' }))
  await userEvent.click(within(editor).getByRole('button', { name: 'Save script' }))

  await waitFor(() => expect(saved).not.toBeNull())
  const turnsSaved = (saved as { turns: { speaker: string; text: string }[] }).turns
  expect(turnsSaved.map((t) => t.text)).toEqual(['Closing words.', 'Zebras graze on grass.'])
  await waitFor(() =>
    expect(within(view).queryByRole('region', { name: 'Script editor' })).not.toBeInTheDocument(),
  )

  await userEvent.click(within(view).getByRole('button', { name: 'Re-synthesize audio' }))
  await waitFor(() =>
    expect(
      calls.some((c) => c.method === 'POST' && c.path.endsWith('/artifacts/au/resynthesize')),
    ).toBe(true),
  )
})

it('shows the outdated banner when the script changed after the audio was made', async () => {
  mockBackend(
    base({
      'GET /notebooks/n1/artifacts/au': audioDetail({ data: transcript({ outdated: true }) }),
    }),
  )
  const { view } = await openAudio()
  expect(within(view).getByRole('status')).toHaveTextContent('The script changed')
})

it('creates an audio overview with the chosen length and format and the focus', async () => {
  const calls = mockBackend(
    base({
      'GET /notebooks/n1/artifacts': [],
      'POST /notebooks/n1/artifacts': audioDetail(),
    }),
  )
  render(<App />)
  const section = await screen.findByRole('region', { name: 'Audio overview' })
  const length = within(section).getByRole('combobox', { name: 'Length' })
  expect(
    within(length)
      .getAllByRole('option')
      .map((o) => o.textContent),
  ).toEqual(['Short (about 5 minutes)', 'Default (about 10 minutes)', 'Long (about 20 minutes)'])
  await userEvent.selectOptions(length, 'long')
  await userEvent.selectOptions(within(section).getByRole('combobox', { name: 'Format' }), 'debate')
  await userEvent.type(screen.getByLabelText('Focus (optional)'), 'migration')
  await userEvent.click(within(section).getByRole('button', { name: 'Generate audio overview' }))
  await waitFor(() =>
    expect(
      calls.find((c) => c.method === 'POST' && c.path === '/notebooks/n1/artifacts')?.body,
    ).toEqual({
      kind: 'audio_overview',
      focus: 'migration',
      options: { length: 'long', format: 'debate' },
    }),
  )
})

it('explains why the audio overview cannot be made yet', async () => {
  mockBackend(
    base({
      'GET /notebooks/n1/artifacts': [],
      'GET /capabilities': caps({
        audio_overview: {
          ready: false,
          problems: ['Install espeak-ng.', 'Download the voice model.'],
        },
      }),
    }),
  )
  render(<App />)
  const section = await screen.findByRole('region', { name: 'Audio overview' })
  const button = within(section).getByRole('button', { name: 'Generate audio overview' })
  await waitFor(() => expect(button).toBeDisabled())
  expect(
    within(within(section).getByRole('list', { name: 'What is missing' }))
      .getAllByRole('listitem')
      .map((i) => i.textContent),
  ).toEqual(['Install espeak-ng.', 'Download the voice model.'])
})

it('exports the audio as MP3', async () => {
  mockBackend(base())
  const { view } = await openAudio()
  await userEvent.click(within(view).getByRole('button', { name: 'Export' }))
  expect(
    within(view)
      .getAllByRole('menuitem')
      .map((m) => m.textContent),
  ).toEqual([expect.stringContaining('MP3')])
})
