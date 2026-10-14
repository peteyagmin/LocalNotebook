import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { App, remoteHost } from './App'
import type { Settings } from './api'

const base: Settings = {
  chat_model: '',
  embedding_model: '',
  stt_model: '',
  tts_voice_a: '',
  tts_voice_b: '',
  llm_base_url: 'http://127.0.0.1:11434/v1',
  llm_api_key: '',
  setup_completed: true,
}

function mockApi(settings: Settings) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const body = url.endsWith('/setup/checks')
        ? {
            checks: [
              {
                id: 'ffmpeg',
                label: 'ffmpeg installed',
                ok: false,
                detail: 'Not found',
                fix: 'Install it',
              },
            ],
          }
        : settings
      return new Response(JSON.stringify(body), { status: 200 })
    }),
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('remoteHost', () => {
  it('is null for loopback and set otherwise', () => {
    expect(remoteHost('http://127.0.0.1:11434/v1')).toBeNull()
    expect(remoteHost('http://localhost:11434/v1')).toBeNull()
    expect(remoteHost('http://[::1]:11434/v1')).toBeNull()
    expect(remoteHost('https://api.example.com/v1')).toBe('api.example.com')
  })
})

describe('App', () => {
  it('shows the three panes and can collapse one', async () => {
    mockApi(base)
    render(<App />)
    for (const name of ['Sources', 'Chat', 'Studio']) {
      expect(await screen.findByRole('region', { name })).toBeInTheDocument()
    }
    await userEvent.click(screen.getByRole('button', { name: 'Collapse Sources pane' }))
    expect(screen.getByRole('button', { name: 'Expand Sources pane' })).toBeInTheDocument()
  })

  it('warns when the model server is not loopback', async () => {
    mockApi({ ...base, llm_base_url: 'https://api.example.com/v1' })
    render(<App />)
    expect(
      await screen.findByText('AI requests are being sent to api.example.com.'),
    ).toBeInTheDocument()
  })

  it('shows the setup wizard checks before setup is completed', async () => {
    mockApi({ ...base, setup_completed: false })
    render(<App />)
    expect(await screen.findByText('ffmpeg installed')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Install it')).toBeInTheDocument())
  })
})
