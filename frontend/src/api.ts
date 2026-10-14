// Hand-typed API client for /api/v1 (spec §11.2). Every request carries the per-launch token.

export interface Settings {
  chat_model: string
  embedding_model: string
  stt_model: string
  tts_voice_a: string
  tts_voice_b: string
  llm_base_url: string
  llm_api_key: string
  setup_completed: boolean
}

export interface SetupCheck {
  id: string
  label: string
  ok: boolean
  detail: string
  fix: string | null
}

export interface ConnectionResult {
  ok: boolean
  message: string
  models: string[]
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message)
  }
}

const TOKEN_KEY = 'lnb_token'

/** Take the token from the URL fragment (set by the launcher), keep it for the session. */
export function captureToken(): void {
  const match = /(?:^#|&)token=([^&]+)/.exec(window.location.hash)
  if (!match) return
  try {
    sessionStorage.setItem(TOKEN_KEY, decodeURIComponent(match[1]))
  } catch {
    /* storage unavailable: token stays in memory only for this load */
  }
  history.replaceState(null, '', window.location.pathname + window.location.search)
}

function token(): string {
  try {
    return sessionStorage.getItem(TOKEN_KEY) ?? ''
  } catch {
    return ''
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const resp = await fetch(`/api/v1${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token()}`,
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!resp.ok) {
    let code = 'http_error'
    let message = `Request failed (${resp.status}).`
    try {
      const data = await resp.json()
      code = data.error.code
      message = data.error.message
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(resp.status, code, message)
  }
  return resp.json() as Promise<T>
}

export const api = {
  getSettings: () => request<Settings>('GET', '/settings'),
  updateSettings: (changes: Partial<Settings>) => request<Settings>('PUT', '/settings', changes),
  testConnection: () => request<ConnectionResult>('POST', '/settings/test-connection'),
  getSetupChecks: () => request<{ checks: SetupCheck[] }>('GET', '/setup/checks'),
}
