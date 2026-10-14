import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { App } from '../App'
import {
  artifact,
  artifactDetail,
  baseSettings,
  chatMessage,
  flashcardsData,
  mindMapData,
  mockBackend,
  notebook,
  openSse,
  source,
  timelineData,
  type Routes,
} from '../test/backend'
import { FlashcardsView } from './FlashcardsView'
import { MindMapView, askQuestion } from './MindMapView'
import { TimelineView } from './TimelineView'

const citations = chatMessage().citations
const noop = () => {}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

// --- timeline (FR-5.5) -----------------------------------------------------------------------

it('renders timeline events in order with citations, and the cast', () => {
  render(<TimelineView data={timelineData} citations={citations} onOpenCitation={noop} />)
  const items = within(screen.getByRole('list', { name: 'Timeline events' })).getAllByRole(
    'listitem',
  )
  expect(items.map((li) => li.textContent)).toEqual([
    expect.stringContaining('1874'),
    expect.stringContaining('March 1902'),
  ])
  expect(within(items[0]).getByText('Port founded')).toBeInTheDocument()
  expect(within(items[0]).getByRole('button', { name: 'Citation 1: Doc.pdf' })).toBeInTheDocument()
  const cast = screen.getByRole('region', { name: 'Key people and entities' })
  expect(within(cast).getByText('Henrik Aldane')).toBeInTheDocument()
  expect(within(cast).getByText(/founder/)).toBeInTheDocument()
})

it('says "No dated events found" when there are none', () => {
  render(<TimelineView data={{ events: [], cast: [] }} citations={[]} onOpenCitation={noop} />)
  expect(screen.getByText('No dated events found')).toBeInTheDocument()
  expect(screen.queryByRole('list')).not.toBeInTheDocument()
})

// --- flashcards and quiz (FR-5.7) --------------------------------------------------------------

it('flips flashcards and moves between them', async () => {
  render(<FlashcardsView data={flashcardsData} citations={citations} onOpenCitation={noop} />)
  const card = screen.getByTestId('card')
  expect(card).toHaveAttribute('data-flipped', 'false')
  expect(screen.getByText('Card 1 of 3')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Previous card' })).toBeDisabled()

  await userEvent.click(screen.getByRole('button', { name: /Flashcard front: What do zebras eat/ }))
  expect(card).toHaveAttribute('data-flipped', 'true')
  const back = screen.getByRole('button', { name: /Flashcard back: Grass/ })
  expect(back).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Citation 1: Doc.pdf' })).toBeInTheDocument()
  await userEvent.click(back)
  expect(card).toHaveAttribute('data-flipped', 'false')

  await userEvent.click(screen.getByRole('button', { name: 'Next card' }))
  expect(screen.getByText('Card 2 of 3')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /front: Where do they live/ })).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Next card' }))
  expect(screen.getByRole('button', { name: 'Next card' })).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: 'Previous card' }))
  expect(screen.getByText('Card 2 of 3')).toBeInTheDocument()
})

it('runs the quiz with feedback, citations, and a final score', async () => {
  render(<FlashcardsView data={flashcardsData} citations={citations} onOpenCitation={noop} />)
  await userEvent.click(screen.getByRole('tab', { name: 'Quiz' }))
  expect(screen.getByText('Question 1 of 3')).toBeInTheDocument()

  await userEvent.click(screen.getByRole('radio', { name: 'B1' })) // correct
  expect(screen.getByRole('status')).toHaveTextContent('Correct!')
  expect(screen.getByRole('status')).toHaveTextContent('Because one.')
  expect(
    within(screen.getByRole('status')).getByRole('button', { name: 'Citation 1: Doc.pdf' }),
  ).toBeInTheDocument()
  expect(screen.getByRole('radio', { name: 'A1' })).toBeDisabled() // locked after answering
  await userEvent.click(screen.getByRole('button', { name: 'Next question' }))

  await userEvent.click(screen.getByRole('radio', { name: 'C2' })) // wrong (correct is A2)
  expect(screen.getByRole('status')).toHaveTextContent('Not quite.')
  expect(screen.getByText('Correct answer')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Next question' }))

  await userEvent.click(screen.getByRole('radio', { name: 'D3' })) // correct
  await userEvent.click(screen.getByRole('button', { name: 'See score' }))
  expect(screen.getByRole('status')).toHaveTextContent('You scored 2 of 3')

  await userEvent.click(screen.getByRole('button', { name: 'Retake quiz' }))
  expect(screen.getByText('Question 1 of 3')).toBeInTheDocument()
})

// --- mind map (FR-5.6) --------------------------------------------------------------------------

it('builds the question sent to chat from the node and its parent path', () => {
  expect(askQuestion('Zebras', [])).toBe('Tell me about Zebras')
  expect(askQuestion('Grass', ['Zebras', 'Diet'])).toBe(
    'Tell me about Grass in the context of Zebras > Diet',
  )
})

it('shows the tree, collapses and expands branches, and asks the chat about a node', async () => {
  const onAsk = vi.fn()
  render(<MindMapView root={mindMapData.root} onAsk={onAsk} />)
  expect(await screen.findByRole('button', { name: 'Ask about Zebras' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Ask about Grass' })).toBeInTheDocument()

  await userEvent.click(screen.getByRole('button', { name: 'Collapse Diet' }))
  expect(screen.queryByRole('button', { name: 'Ask about Grass' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Expand Diet' })).toHaveAttribute(
    'aria-expanded',
    'false',
  )
  expect(screen.getByRole('button', { name: 'Ask about Habitat' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Collapse Habitat/ })).not.toBeInTheDocument() // leaf

  await userEvent.click(screen.getByRole('button', { name: 'Expand Diet' }))
  await userEvent.click(screen.getByRole('button', { name: 'Ask about Grass' }))
  expect(onAsk).toHaveBeenCalledWith('Tell me about Grass in the context of Zebras > Diet')
  await userEvent.click(screen.getByRole('button', { name: 'Ask about Zebras' }))
  expect(onAsk).toHaveBeenLastCalledWith('Tell me about Zebras')
})

// --- in the app ---------------------------------------------------------------------------------

beforeEach(() => {
  window.location.hash = '#/notebooks/n1'
})

const base = (extra: Routes = {}): Routes => ({
  'GET /settings': baseSettings,
  'GET /notebooks/n1': notebook(),
  'GET /notebooks/n1/sources': [source()],
  'GET /notebooks/n1/chat': [],
  'GET /notebooks/n1/chat/starters': { questions: [] },
  'GET /notebooks/n1/notes': [],
  ...extra,
})

/** The artifact's entry in the "Generated" list (the create buttons share the same names). */
async function openFromList(title: string) {
  const list = await screen.findByRole('region', { name: 'Artifacts' })
  return within(list).findByRole('button', { name: title })
}

async function openArtifact(
  kind: 'timeline' | 'mind_map' | 'flashcards',
  data: unknown,
  title: string,
) {
  const routes: Routes = base({
    'GET /notebooks/n1/artifacts': [artifact({ kind, title })],
    'GET /notebooks/n1/artifacts/a1': artifactDetail({
      kind,
      title,
      format: 'json',
      content: '',
      data: data as never,
    }),
  })
  return routes
}

it('offers the right export formats for each structured artifact', async () => {
  const expected: Record<string, string[]> = {
    timeline: ['JSON (.json)', 'Markdown (.md)', 'Word (.docx)', 'PDF (.pdf)'],
    mind_map: ['PNG image (.png)', 'JSON (.json)'],
    flashcards: ['Flashcards (.csv)', 'Quiz (.csv)', 'JSON (.json)'],
  }
  const cases = [
    ['timeline', timelineData, 'Timeline'],
    ['mind_map', mindMapData, 'Mind map'],
    ['flashcards', flashcardsData, 'Flashcards & quiz'],
  ] as const
  for (const [kind, data, title] of cases) {
    mockBackend(await openArtifact(kind, data, title))
    const { unmount } = render(<App />)
    await userEvent.click(await openFromList(title))
    const view = await screen.findByRole('region', { name: `Artifact: ${title}` })
    await userEvent.click(within(view).getByRole('button', { name: 'Export' }))
    expect(
      within(view)
        .getAllByRole('menuitem')
        .map((m) => m.textContent),
    ).toEqual(expected[kind])
    unmount()
  }
})

it('sends the mind map click to the chat', async () => {
  const sse = openSse()
  const calls = mockBackend({
    ...(await openArtifact('mind_map', mindMapData, 'Mind map')),
    'POST /notebooks/n1/chat': sse.response,
  })
  render(<App />)
  await userEvent.click(await openFromList('Mind map'))
  await userEvent.click(await screen.findByRole('button', { name: 'Ask about Grass' }))
  await waitFor(() =>
    expect(calls.find((c) => c.method === 'POST' && c.path === '/notebooks/n1/chat')?.body).toEqual(
      {
        question: 'Tell me about Grass in the context of Zebras > Diet',
      },
    ),
  )
  expect(
    await screen.findByText('Tell me about Grass in the context of Zebras > Diet'),
  ).toBeInTheDocument()
  sse.close()
})
