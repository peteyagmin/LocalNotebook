import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { App } from '../App'
import {
  baseSettings,
  chatMessage,
  mockBackend,
  notebook,
  openSse,
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
  ...extra,
})

const cite = chatMessage().citations

it('shows starter questions when the chat is empty and sends one on click', async () => {
  const calls = mockBackend(
    base({
      'GET /notebooks/n1/chat/starters': { questions: ['What are zebras?', 'Where do they live?'] },
      'POST /notebooks/n1/chat': sseResponse([
        { type: 'done', message: chatMessage({ content: 'They are striped.', citations: [] }) },
      ]),
    }),
  )
  render(<App />)
  await userEvent.click(await screen.findByRole('button', { name: 'What are zebras?' }))
  expect(await screen.findByText('They are striped.')).toBeInTheDocument()
  expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ question: 'What are zebras?' })
})

it('streams an answer with citation chips; hover text names the source; click opens the passage', async () => {
  mockBackend(
    base({
      'POST /notebooks/n1/chat': sseResponse([
        {
          type: 'user_message',
          message: chatMessage({ id: 'u1', role: 'user', content: 'Q?', citations: [] }),
        },
        { type: 'sources', citations: cite },
        { type: 'token', text: 'Zebras graze ' },
        { type: 'token', text: '[1].' },
        { type: 'done', message: chatMessage() },
        { type: 'suggestions', message_id: 'm1', questions: ['What else?'] },
      ]),
      'GET /notebooks/n1/sources/s1/content': {
        text: 'Zebras graze on grass in herds.',
        segments: [{ start: 0, end: 31, page: 1, heading_path: null }],
        page_count: 1,
      },
    }),
  )
  render(<App />)
  await userEvent.type(await screen.findByLabelText('Ask a question'), 'Q?{Enter}')
  const chip = await screen.findByRole('button', { name: 'Citation 1: Doc.pdf' })
  const tooltip = within(chip.parentElement!).getByRole('tooltip')
  expect(tooltip).toHaveTextContent('Doc.pdf')
  expect(tooltip).toHaveTextContent('Zebras graze on grass in herds.')
  await userEvent.click(chip)
  const viewer = await screen.findByRole('dialog', { name: 'Source: Doc.pdf' })
  const mark = await within(viewer).findByText('Zebras graze on grass in herds.', {
    selector: 'mark',
  })
  expect(mark).toBeInTheDocument()
})

it('shows follow-up suggestions after the last answer and sends them', async () => {
  const calls = mockBackend(
    base({
      'GET /notebooks/n1/chat': [
        chatMessage({ id: 'u', role: 'user', content: 'Q', citations: [] }),
        chatMessage({ suggestions: ['What else?'] }),
      ],
      'POST /notebooks/n1/chat': sseResponse([
        { type: 'done', message: chatMessage({ id: 'm2', content: 'More.', citations: [] }) },
      ]),
    }),
  )
  render(<App />)
  await userEvent.click(await screen.findByRole('button', { name: 'What else?' }))
  await waitFor(() =>
    expect(calls.find((c) => c.method === 'POST' && c.path.endsWith('/chat'))?.body).toEqual({
      question: 'What else?',
    }),
  )
})

it('Enter sends and Shift+Enter inserts a newline', async () => {
  const calls = mockBackend(
    base({
      'POST /notebooks/n1/chat': sseResponse([
        { type: 'done', message: chatMessage({ citations: [] }) },
      ]),
    }),
  )
  render(<App />)
  const input = await screen.findByLabelText('Ask a question')
  await userEvent.type(input, 'line one{Shift>}{Enter}{/Shift}line two')
  expect(input).toHaveValue('line one\nline two')
  expect(calls.some((c) => c.method === 'POST')).toBe(false)
  await userEvent.type(input, '{Enter}')
  await waitFor(() =>
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({
      question: 'line one\nline two',
    }),
  )
})

it('Stop ends generation and the partial answer is kept and marked stopped', async () => {
  const sse = openSse()
  const calls = mockBackend(
    base({
      'POST /notebooks/n1/chat': sse.response,
      'POST /notebooks/n1/chat/stop': () => {
        sse.push({
          type: 'done',
          message: chatMessage({ content: 'Zebras graze', citations: [], status: 'stopped' }),
        })
        sse.close()
        return undefined
      },
    }),
  )
  render(<App />)
  await userEvent.type(await screen.findByLabelText('Ask a question'), 'Q?{Enter}')
  sse.push({ type: 'token', text: 'Zebras graze' })
  expect(await screen.findByText('Zebras graze')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Stop' }))
  await waitFor(() => expect(calls.some((c) => c.path.endsWith('/chat/stop'))).toBe(true))
  expect(await screen.findByText('Stopped')).toBeInTheDocument()
  expect(screen.getByText('Zebras graze')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument()
})

it('shows a clear error with a link to Settings when the model server fails', async () => {
  mockBackend(
    base({
      'POST /notebooks/n1/chat': sseResponse([
        {
          type: 'error',
          code: 'llm_error',
          message: 'Could not reach the model server: ConnectError.',
        },
      ]),
    }),
  )
  render(<App />)
  await userEvent.type(await screen.findByLabelText('Ask a question'), 'Q?{Enter}')
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('Could not reach the model server')
  expect(within(alert).getByRole('link', { name: 'Open Settings' })).toHaveAttribute(
    'href',
    '#/settings',
  )
})

it('renders model output as sanitized Markdown: no raw HTML, no images, safe links', async () => {
  mockBackend(
    base({
      'GET /notebooks/n1/chat': [
        chatMessage({
          citations: [],
          content:
            '**bold** <script>window.__pwned = true</script><b>raw</b> ![x](http://evil.test/p.png) [site](http://example.test) [bad](javascript:alert(1))',
        }),
      ],
    }),
  )
  const { container } = render(<App />)
  expect(await screen.findByText('bold')).toContainHTML('bold')
  expect(container.querySelector('script')).toBeNull()
  expect(container.querySelector('img')).toBeNull()
  expect(container.querySelector('b')).toBeNull()
  expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined()
  const link = screen.getByRole('link', { name: 'site' })
  expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
  const bad = container.querySelector('a[href^="javascript"]')
  expect(bad).toBeNull()
})

it('marks citations to removed sources and does not open them', async () => {
  mockBackend(
    base({
      'GET /notebooks/n1/chat': [chatMessage({ citations: [{ ...cite[0], removed: true }] })],
    }),
  )
  render(<App />)
  const chip = await screen.findByRole('button', { name: 'Citation 1: source removed' })
  expect(chip).toBeDisabled()
})

it('saves chat settings and confirms before clearing the chat', async () => {
  const calls = mockBackend(
    base({
      'GET /notebooks/n1/chat': [chatMessage({ citations: [] })],
      'GET /notebooks/n1/chat/settings': { response_style: 'default', custom_instruction: '' },
      'PUT /notebooks/n1/chat/settings': (b: unknown) => b,
      'DELETE /notebooks/n1/chat': undefined,
    }),
  )
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  render(<App />)
  await userEvent.click(await screen.findByRole('button', { name: 'Chat settings' }))
  const form = await screen.findByRole('form', { name: 'Chat settings' })
  await userEvent.selectOptions(within(form).getByLabelText('Response style'), 'concise')
  await userEvent.type(within(form).getByLabelText(/Custom instruction/), 'Be kind')
  await userEvent.click(within(form).getByRole('button', { name: 'Save' }))
  await waitFor(() =>
    expect(
      calls.find((c) => c.method === 'PUT' && c.path.endsWith('/chat/settings'))?.body,
    ).toEqual({
      response_style: 'concise',
      custom_instruction: 'Be kind',
    }),
  )
  await userEvent.click(screen.getByRole('button', { name: 'Clear chat' }))
  expect(confirm).toHaveBeenCalled()
  expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
  confirm.mockReturnValue(true)
  await userEvent.click(screen.getByRole('button', { name: 'Clear chat' }))
  await waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true))
})

it('searches sources, highlights terms, opens the passage; Ctrl+K focuses the box', async () => {
  mockBackend(
    base({
      'GET /notebooks/n1/search': [
        {
          chunk_id: 'c1',
          source_id: 's1',
          source_name: 'Doc.pdf',
          location: { page: 3, heading_path: null, char_start: 0, char_end: 31 },
          excerpt: 'The quokka is a small marsupial.',
          char_start: 0,
          char_end: 31,
        },
      ],
      'GET /notebooks/n1/sources/s1/content': {
        text: 'The quokka is a small marsupial.',
        segments: [{ start: 0, end: 32, page: 3, heading_path: null }],
        page_count: 3,
      },
    }),
  )
  render(<App />)
  const box = await screen.findByLabelText('Search sources')
  expect(box).not.toHaveFocus()
  await userEvent.keyboard('{Control>}k{/Control}')
  expect(box).toHaveFocus()
  await userEvent.type(box, 'quokka')
  const results = await screen.findByRole('region', { name: 'Search results' })
  expect(await within(results).findByText('quokka', { selector: 'mark' })).toBeInTheDocument()
  expect(within(results).getByText('page 3')).toBeInTheDocument()
  await userEvent.click(within(results).getByRole('button', { name: /Doc\.pdf/ }))
  expect(await screen.findByRole('dialog', { name: 'Source: Doc.pdf' })).toBeInTheDocument()
})
