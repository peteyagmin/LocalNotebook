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
  max_sources_per_notebook: number
  max_upload_mb: number
  retrieval_top_k: number
  context_window_tokens: number
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

export interface Notebook {
  id: string
  name: string
  created_at: string
  updated_at: string
  source_count: number
  size_bytes: number
}

export type SourceState = 'queued' | 'processing' | 'ready' | 'failed'

export interface Source {
  id: string
  name: string
  type: 'pdf' | 'docx' | 'txt' | 'md' | 'text'
  size_bytes: number
  state: SourceState
  stage: string | null
  progress: number
  error: string | null
  enabled: boolean
  char_count: number | null
  page_count: number | null
  guide: { summary: string; topics: string[] } | null
}

export interface SourceContent {
  text: string
  segments: { start: number; end: number; page: number | null; heading_path: string[] | null }[]
  page_count: number | null
}

export interface Citation {
  label: number
  chunk_id: string
  source_id: string
  source_name: string
  excerpt: string
  location: {
    page: number | null
    heading_path: string[] | null
    char_start: number
    char_end: number
  }
  removed?: boolean
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations: Citation[]
  suggestions: string[]
  status: 'complete' | 'stopped' | 'error'
  created_at: string
}

export type ChatEvent =
  | { type: 'user_message'; message: ChatMessage }
  | { type: 'sources'; citations: Citation[] }
  | { type: 'token'; text: string }
  | { type: 'done'; message: ChatMessage }
  | { type: 'suggestions'; message_id: string; questions: string[] }
  | { type: 'error'; code: string; message: string }

export interface ChatSettings {
  response_style: 'default' | 'concise' | 'detailed' | 'learning_guide'
  custom_instruction: string
}

export interface NoteSummary {
  id: string
  title: string
  preview: string
  updated_at: string
}

export interface Note {
  id: string
  title: string
  content: string
  citations: Citation[]
  created_at: string
  updated_at: string
}

export type ArtifactKind = 'summary' | 'briefing' | 'study_guide' | 'faq'
export type ArtifactState = 'queued' | 'running' | 'ready' | 'failed' | 'cancelled'

export interface Artifact {
  id: string
  kind: ArtifactKind
  title: string
  state: ArtifactState
  stage: string | null
  progress: number
  error: string | null
  focus: string
  has_content: boolean
  stale: boolean
  created_at: string
  updated_at: string
}

export interface ArtifactDetail extends Artifact {
  content: string
  citations: Citation[]
}

export interface SearchResult {
  kind: 'source' | 'note'
  note_id: string | null
  chunk_id: string
  source_id: string | null
  source_name: string
  location: Citation['location']
  excerpt: string
  char_start: number
  char_end: number
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

async function throwIfError(resp: Response): Promise<void> {
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
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData
  const resp = await fetch(`/api/v1${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token()}`,
      ...(body === undefined || isForm ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  })
  await throwIfError(resp)
  if (resp.status === 204) return undefined as T
  return resp.json() as Promise<T>
}

/** Read a Server-Sent Events stream with fetch (EventSource cannot send the auth header). */
async function stream<T>(
  path: string,
  onEvent: (data: T) => void,
  signal: AbortSignal,
  body?: unknown,
) {
  const resp = await fetch(`/api/v1${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: {
      Authorization: `Bearer ${token()}`,
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  })
  await throwIfError(resp)
  const reader = resp.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) return
    buffer += decoder.decode(value, { stream: true })
    let end: number
    while ((end = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, end)
      buffer = buffer.slice(end + 2)
      const line = block.split('\n').find((l) => l.startsWith('data: '))
      if (line) onEvent(JSON.parse(line.slice(6)) as T)
    }
  }
}

const nb = (id: string) => `/notebooks/${id}`

export const api = {
  listNotebooks: () => request<Notebook[]>('GET', '/notebooks'),
  getNotebook: (id: string) => request<Notebook>('GET', nb(id)),
  createNotebook: (name: string) => request<Notebook>('POST', '/notebooks', { name }),
  renameNotebook: (id: string, name: string) => request<Notebook>('PATCH', nb(id), { name }),
  duplicateNotebook: (id: string) => request<Notebook>('POST', `${nb(id)}/duplicate`),
  deleteNotebook: (id: string) => request<void>('DELETE', nb(id)),

  listSources: (id: string) => request<Source[]>('GET', `${nb(id)}/sources`),
  streamSources: (id: string, onEvent: (s: Source[]) => void, signal: AbortSignal) =>
    stream<Source[]>(`${nb(id)}/sources/stream`, onEvent, signal),
  uploadFiles: (id: string, files: File[]) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return request<Source[]>('POST', `${nb(id)}/sources/files`, form)
  },
  pasteText: (id: string, name: string, text: string) =>
    request<Source[]>('POST', `${nb(id)}/sources/text`, { name, text }),
  setSourceEnabled: (id: string, sourceId: string, enabled: boolean) =>
    request<Source>('PATCH', `${nb(id)}/sources/${sourceId}`, { enabled }),
  setAllSourcesEnabled: (id: string, enabled: boolean) =>
    request<Source[]>('POST', `${nb(id)}/sources/enabled`, { enabled }),
  retrySource: (id: string, sourceId: string) =>
    request<Source>('POST', `${nb(id)}/sources/${sourceId}/retry`),
  deleteSource: (id: string, sourceId: string) =>
    request<void>('DELETE', `${nb(id)}/sources/${sourceId}`),
  getChat: (id: string) => request<ChatMessage[]>('GET', `${nb(id)}/chat`),
  clearChat: (id: string) => request<void>('DELETE', `${nb(id)}/chat`),
  askStream: (id: string, question: string, onEvent: (e: ChatEvent) => void, signal: AbortSignal) =>
    stream<ChatEvent>(`${nb(id)}/chat`, onEvent, signal, { question }),
  stopChat: (id: string) => request<void>('POST', `${nb(id)}/chat/stop`),
  getStarters: (id: string) => request<{ questions: string[] }>('GET', `${nb(id)}/chat/starters`),
  getChatSettings: (id: string) => request<ChatSettings>('GET', `${nb(id)}/chat/settings`),
  putChatSettings: (id: string, settings: ChatSettings) =>
    request<ChatSettings>('PUT', `${nb(id)}/chat/settings`, settings),
  search: (id: string, q: string) =>
    request<SearchResult[]>('GET', `${nb(id)}/search?q=${encodeURIComponent(q)}`),
  saveMessageToNote: (id: string, messageId: string) =>
    request<Note>('POST', `${nb(id)}/chat/messages/${messageId}/save-note`),

  listNotes: (id: string) => request<NoteSummary[]>('GET', `${nb(id)}/notes`),
  getNote: (id: string, noteId: string) => request<Note>('GET', `${nb(id)}/notes/${noteId}`),
  createNote: (id: string, title = '', content = '') =>
    request<Note>('POST', `${nb(id)}/notes`, { title, content }),
  updateNote: (id: string, noteId: string, patch: { title?: string; content?: string }) =>
    request<Note>('PATCH', `${nb(id)}/notes/${noteId}`, patch),
  deleteNote: (id: string, noteId: string) => request<void>('DELETE', `${nb(id)}/notes/${noteId}`),
  combineNotes: (id: string, noteIds: string[]) =>
    request<Note>('POST', `${nb(id)}/notes/combine`, { note_ids: noteIds }),
  summarizeNotes: (id: string, noteIds: string[]) =>
    request<Note>('POST', `${nb(id)}/notes/summarize`, { note_ids: noteIds }),
  convertNotesToSources: (id: string, noteIds: string[]) =>
    request<Source[]>('POST', `${nb(id)}/notes/convert-to-source`, { note_ids: noteIds }),

  listArtifacts: (id: string) => request<Artifact[]>('GET', `${nb(id)}/artifacts`),
  streamArtifacts: (id: string, onEvent: (a: Artifact[]) => void, signal: AbortSignal) =>
    stream<Artifact[]>(`${nb(id)}/artifacts/stream`, onEvent, signal),
  createArtifact: (id: string, kind: ArtifactKind, focus: string) =>
    request<ArtifactDetail>('POST', `${nb(id)}/artifacts`, { kind, focus }),
  getArtifact: (id: string, artifactId: string) =>
    request<ArtifactDetail>('GET', `${nb(id)}/artifacts/${artifactId}`),
  regenerateArtifact: (id: string, artifactId: string, focus?: string) =>
    request<ArtifactDetail>('POST', `${nb(id)}/artifacts/${artifactId}/regenerate`, { focus }),
  cancelArtifact: (id: string, artifactId: string) =>
    request<void>('POST', `${nb(id)}/artifacts/${artifactId}/cancel`),
  deleteArtifact: (id: string, artifactId: string) =>
    request<void>('DELETE', `${nb(id)}/artifacts/${artifactId}`),
  exportArtifact: async (id: string, artifactId: string, format: 'md' | 'docx' | 'pdf') => {
    const resp = await fetch(`/api/v1${nb(id)}/artifacts/${artifactId}/export?format=${format}`, {
      headers: { Authorization: `Bearer ${token()}` },
    })
    await throwIfError(resp)
    const disposition = resp.headers.get('Content-Disposition') ?? ''
    const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `export.${format}`
    return { blob: await resp.blob(), filename }
  },

  getSourceContent: (id: string, sourceId: string) =>
    request<SourceContent>('GET', `${nb(id)}/sources/${sourceId}/content`),

  getSettings: () => request<Settings>('GET', '/settings'),
  updateSettings: (changes: Partial<Settings>) => request<Settings>('PUT', '/settings', changes),
  testConnection: () => request<ConnectionResult>('POST', '/settings/test-connection'),
  getSetupChecks: () => request<{ checks: SetupCheck[] }>('GET', '/setup/checks'),
}
