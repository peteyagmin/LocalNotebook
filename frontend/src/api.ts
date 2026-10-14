// Hand-typed API client for /api/v1 (spec §11.2). Every request carries the per-launch token.

export interface Settings {
  chat_model: string
  embedding_model: string
  stt_model: string
  tts_model: string
  tts_voice_a: string
  tts_voice_b: string
  llm_base_url: string
  llm_api_key: string
  setup_completed: boolean
  max_sources_per_notebook: number
  max_upload_mb: number
  retrieval_top_k: number
  context_window_tokens: number
  allow_web_import: boolean
  allow_discover: boolean
  allow_model_downloads: boolean
  transcribe_uncaptioned_videos: boolean
  searxng_url: string
  theme: 'system' | 'light' | 'dark'
  font_size: number
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
  /** FR-8.5: built with another embedding model than the one now selected. */
  index_stale?: boolean
  reindexing?: boolean
}

export type SourceState = 'queued' | 'processing' | 'ready' | 'failed'

export interface Source {
  id: string
  name: string
  type:
    'pdf' | 'docx' | 'txt' | 'md' | 'text' | 'html' | 'epub' | 'image' | 'audio' | 'web' | 'youtube'
  url: string | null
  fetched_at: string | null
  version_count: number
  meta: {
    title?: string
    channel?: string
    description?: string
    duration?: number | null
    video_id?: string
    transcript?: 'captions' | 'transcription'
  }
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
  segments: {
    start: number
    end: number
    page: number | null
    heading_path: string[] | null
    start_s?: number | null
    end_s?: number | null
  }[]
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
    start_seconds?: number
    end_seconds?: number
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

export type ArtifactKind =
  | 'summary'
  | 'briefing'
  | 'study_guide'
  | 'faq'
  | 'timeline'
  | 'mind_map'
  | 'flashcards'
  | 'audio_overview'

export type AudioLength = 'short' | 'default' | 'long'
export type AudioFormat = 'deep_dive' | 'brief' | 'debate' | 'critique'
export interface AudioOptions {
  length: AudioLength
  format: AudioFormat
}

export interface AudioTurn {
  speaker: 'A' | 'B'
  text: string
  chunk_ids: string[]
  start: number | null
  end: number | null
}

export interface AudioTranscript {
  title: string
  options: AudioOptions
  turns: AudioTurn[]
  duration: number | null
  outdated: boolean
}

export interface TimelineData {
  events: {
    date: string
    iso_date: string
    title: string
    description: string
    sources: number[]
  }[]
  cast: { name: string; role: string; sources: number[] }[]
}

export interface MindNodeData {
  label: string
  sources: number[]
  children: MindNodeData[]
}

export interface FlashcardsData {
  flashcards: { front: string; back: string; sources: number[] }[]
  quiz: {
    question: string
    options: string[]
    correct_index: number
    explanation: string
    sources: number[]
  }[]
}

export type ArtifactFormat =
  'md' | 'docx' | 'pdf' | 'json' | 'png' | 'csv-flashcards' | 'csv-quiz' | 'mp3'
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
  options: AudioOptions | null
  has_content: boolean
  stale: boolean
  created_at: string
  updated_at: string
}

export interface ArtifactDetail extends Artifact {
  format: 'markdown' | 'json' | 'audio'
  content: string
  data: TimelineData | { root: MindNodeData } | FlashcardsData | AudioTranscript | null
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

export interface TtsStatus {
  model: string
  voices: string[]
  configured: boolean
  installed: boolean
  downloads_allowed: boolean
  espeak: boolean
  ffmpeg: boolean
  state: 'idle' | 'downloading' | 'error'
  progress?: number | null
  error?: string | null
}

export interface SourceVersion {
  version: number
  fetched_at: string | null
  char_count: number | null
}

export interface Capabilities {
  ocr: boolean
  audio_overview: { ready: boolean; problems: string[] }
  stt: { configured: boolean; installed: boolean }
  web_import: boolean
  discover: { allowed: boolean; configured: boolean }
}

export interface SttStatus {
  model: string
  configured: boolean
  installed: boolean
  downloads_allowed: boolean
  state: 'idle' | 'downloading' | 'error'
  progress?: number | null
  error?: string | null
}

export interface DiscoverSuggestion {
  title: string
  url: string
  note: string
  kind: 'web' | 'youtube'
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
  rebuildIndex: (id: string) => request<Notebook>('POST', `${nb(id)}/rebuild-index`),
  importNotebook: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<Notebook>('POST', '/notebooks/import', form)
  },
  exportNotebook: async (id: string) => {
    const resp = await fetch(`/api/v1${nb(id)}/export`, {
      headers: { Authorization: `Bearer ${token()}` },
    })
    await throwIfError(resp)
    const disposition = resp.headers.get('Content-Disposition') ?? ''
    const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? 'notebook.lnb'
    return { blob: await resp.blob(), filename }
  },

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
  createArtifact: (id: string, kind: ArtifactKind, focus: string, options?: AudioOptions) =>
    request<ArtifactDetail>('POST', `${nb(id)}/artifacts`, { kind, focus, options }),
  getArtifact: (id: string, artifactId: string) =>
    request<ArtifactDetail>('GET', `${nb(id)}/artifacts/${artifactId}`),
  regenerateArtifact: (id: string, artifactId: string, focus?: string, options?: AudioOptions) =>
    request<ArtifactDetail>('POST', `${nb(id)}/artifacts/${artifactId}/regenerate`, {
      focus,
      options,
    }),
  saveScript: (
    id: string,
    artifactId: string,
    turns: { speaker: string; text: string; chunk_ids: string[] }[],
  ) => request<ArtifactDetail>('PUT', `${nb(id)}/artifacts/${artifactId}/script`, { turns }),
  resynthesize: (id: string, artifactId: string) =>
    request<ArtifactDetail>('POST', `${nb(id)}/artifacts/${artifactId}/resynthesize`),
  getArtifactAudio: async (id: string, artifactId: string) => {
    const resp = await fetch(`/api/v1${nb(id)}/artifacts/${artifactId}/audio`, {
      headers: { Authorization: `Bearer ${token()}` },
    })
    await throwIfError(resp)
    return resp.blob()
  },
  cancelArtifact: (id: string, artifactId: string) =>
    request<void>('POST', `${nb(id)}/artifacts/${artifactId}/cancel`),
  deleteArtifact: (id: string, artifactId: string) =>
    request<void>('DELETE', `${nb(id)}/artifacts/${artifactId}`),
  exportArtifact: async (id: string, artifactId: string, format: ArtifactFormat) => {
    const resp = await fetch(`/api/v1${nb(id)}/artifacts/${artifactId}/export?format=${format}`, {
      headers: { Authorization: `Bearer ${token()}` },
    })
    await throwIfError(resp)
    const disposition = resp.headers.get('Content-Disposition') ?? ''
    const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `export.${format}`
    return { blob: await resp.blob(), filename }
  },

  importUrls: (id: string, urls: string[]) =>
    request<Source[]>('POST', `${nb(id)}/sources/urls`, { urls }),
  refreshSource: (id: string, sourceId: string) =>
    request<Source>('POST', `${nb(id)}/sources/${sourceId}/refresh`),
  discover: (id: string, topic: string) =>
    request<{ suggestions: DiscoverSuggestion[] }>('POST', `${nb(id)}/discover`, { topic }),
  getCapabilities: () => request<Capabilities>('GET', '/capabilities'),
  getTtsStatus: () => request<TtsStatus>('GET', '/speech/tts'),
  startTtsDownload: () => request<TtsStatus>('POST', '/speech/tts/download', { confirm: true }),
  listVersions: (id: string, sourceId: string) =>
    request<SourceVersion[]>('GET', `${nb(id)}/sources/${sourceId}/versions`),
  getVersionContent: (id: string, sourceId: string, version: number) =>
    request<SourceContent>('GET', `${nb(id)}/sources/${sourceId}/versions/${version}/content`),
  getSttStatus: () => request<SttStatus>('GET', '/speech/stt'),
  startSttDownload: () => request<SttStatus>('POST', '/speech/stt/download', { confirm: true }),
  getSourceContent: (id: string, sourceId: string) =>
    request<SourceContent>('GET', `${nb(id)}/sources/${sourceId}/content`),

  getSettings: () => request<Settings>('GET', '/settings'),
  updateSettings: (changes: Partial<Settings>) => request<Settings>('PUT', '/settings', changes),
  testConnection: () => request<ConnectionResult>('POST', '/settings/test-connection'),
  getSetupChecks: () => request<{ checks: SetupCheck[] }>('GET', '/setup/checks'),
}
