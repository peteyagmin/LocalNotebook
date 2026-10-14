import { useEffect, useRef, useState, type ReactNode } from 'react'
import { api, type ChatSettings, type Citation, type Note } from '../api'
import { useChat } from '../hooks/useChat'
import { AnswerText } from './AnswerText'
import { Pane } from './Pane'

interface ChatPaneProps {
  notebookId: string
  /** Changes when the set of usable sources changes (refreshes the starter questions). */
  sourcesKey: string
  onOpenCitation: (citation: Citation) => void
  /** A message to send as soon as the chat is free (from the mind map). */
  askRequest?: { id: number; text: string } | null
  /** Called with the new note after "Save to note". */
  onNoteSaved: (note: Note) => void
  /** Covers the pane (the source viewer). */
  overlay?: ReactNode
}

type ChatApi = ReturnType<typeof useChat>

export function ChatPane({
  notebookId,
  sourcesKey,
  onOpenCitation,
  onNoteSaved,
  askRequest,
  overlay,
}: ChatPaneProps) {
  const chat = useChat(notebookId, sourcesKey)
  const handled = useRef<number | null>(null)
  useEffect(() => {
    if (!askRequest || handled.current === askRequest.id || chat.busy || chat.messages === null)
      return
    handled.current = askRequest.id
    void chat.send(askRequest.text)
  }, [askRequest, chat])
  return (
    <Pane
      title="Chat"
      side="center"
      collapsed={false}
      onToggle={() => {}}
      overlay={overlay}
      footer={<ChatFooter notebookId={notebookId} chat={chat} />}
    >
      <ChatBody
        notebookId={notebookId}
        chat={chat}
        onOpenCitation={onOpenCitation}
        onNoteSaved={onNoteSaved}
      />
    </Pane>
  )
}

const STYLE_LABELS: Record<ChatSettings['response_style'], string> = {
  default: 'Default',
  concise: 'Concise',
  detailed: 'Detailed',
  learning_guide: 'Learning guide',
}

const buttonClass =
  'rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800'

function ChatBody({
  notebookId,
  chat,
  onOpenCitation,
  onNoteSaved,
}: {
  notebookId: string
  chat: ChatApi
  onOpenCitation: (citation: Citation) => void
  onNoteSaved: (note: Note) => void
}) {
  const [saveError, setSaveError] = useState<string | null>(null)
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set())

  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: 'end' })
  }, [chat.messages, chat.streaming])

  const messages = chat.messages ?? []
  const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant')

  return (
    <div className="space-y-3" aria-live="polite">
      {chat.messages && messages.length === 0 && !chat.busy && (
        <div className="space-y-2">
          <p className="text-neutral-500">Ask a question about your sources.</p>
          {chat.starters.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => void chat.send(q)}
              className="block w-full rounded border border-neutral-300 px-3 py-2 text-left hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {messages.map((m) =>
        m.role === 'user' ? (
          <div key={m.id} className="ml-8 rounded-lg bg-blue-600 px-3 py-2 text-white">
            {m.content}
          </div>
        ) : (
          <div key={m.id} className="mr-4 space-y-1">
            <AnswerText text={m.content} citations={m.citations} onOpenCitation={onOpenCitation} />
            {m.status === 'stopped' && <p className="text-xs text-neutral-500">Stopped</p>}
            <button
              type="button"
              className={buttonClass}
              disabled={savedIds.has(m.id)}
              onClick={() => {
                setSaveError(null)
                api
                  .saveMessageToNote(notebookId, m.id)
                  .then((note) => {
                    setSavedIds(new Set(savedIds).add(m.id))
                    onNoteSaved(note)
                  })
                  .catch((e) => setSaveError(e instanceof Error ? e.message : String(e)))
              }}
            >
              {savedIds.has(m.id) ? 'Saved to notes' : 'Save to note'}
            </button>
            {m.status === 'error' && (
              <p className="text-xs text-neutral-500">Incomplete: the model stopped responding</p>
            )}
            {m === lastAssistant && !chat.busy && m.suggestions.length > 0 && (
              <div className="flex flex-wrap gap-2 pt-1">
                {m.suggestions.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => void chat.send(q)}
                    className="rounded-full border border-neutral-300 px-3 py-1 text-xs hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}
          </div>
        ),
      )}

      {chat.streaming && (
        <div className="mr-4" aria-label="Answer in progress">
          {chat.streaming.text ? (
            <AnswerText
              text={chat.streaming.text}
              citations={chat.streaming.citations}
              onOpenCitation={onOpenCitation}
            />
          ) : (
            <p className="text-neutral-500">Thinking…</p>
          )}
        </div>
      )}

      {saveError && (
        <p role="alert" className="text-red-600">
          {saveError}
        </p>
      )}
      {chat.error && (
        <p role="alert" className="text-red-600">
          {chat.error.message}
          {(chat.error.code === 'not_configured' || chat.error.code === 'llm_error') && (
            <>
              {' '}
              <a href="#/settings" className="underline">
                Open Settings
              </a>
            </>
          )}
        </p>
      )}
      <div ref={endRef} />
    </div>
  )
}

function ChatFooter({ notebookId, chat }: { notebookId: string; chat: ChatApi }) {
  const [text, setText] = useState('')
  const [showSettings, setShowSettings] = useState(false)
  const [settings, setSettings] = useState<ChatSettings>({
    response_style: 'default',
    custom_instruction: '',
  })
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (!showSettings) return
    api
      .getChatSettings(notebookId)
      .then(setSettings)
      .catch(() => {})
  }, [showSettings, notebookId])

  function submit() {
    if (!text.trim() || chat.busy) return
    void chat.send(text)
    setText('')
  }

  return (
    <div className="space-y-2 border-t border-neutral-200 p-3 dark:border-neutral-800">
      {showSettings && (
        <form
          aria-label="Chat settings"
          className="space-y-2 rounded border border-neutral-200 p-2 text-sm dark:border-neutral-800"
          onSubmit={(e) => {
            e.preventDefault()
            void api.putChatSettings(notebookId, settings).then(() => setSaved(true))
          }}
        >
          <label className="block">
            Response style
            <select
              value={settings.response_style}
              onChange={(e) => {
                setSaved(false)
                setSettings({
                  ...settings,
                  response_style: e.target.value as ChatSettings['response_style'],
                })
              }}
              className="mt-1 block w-full rounded border border-neutral-300 bg-transparent px-2 py-1 dark:border-neutral-700 dark:bg-neutral-900"
            >
              {Object.entries(STYLE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            Custom instruction
            <textarea
              rows={3}
              maxLength={1000}
              value={settings.custom_instruction}
              onChange={(e) => {
                setSaved(false)
                setSettings({ ...settings, custom_instruction: e.target.value })
              }}
              className="mt-1 block w-full rounded border border-neutral-300 bg-transparent px-2 py-1 dark:border-neutral-700"
            />
            <span className="text-xs text-neutral-500">
              {settings.custom_instruction.length}/1000
            </span>
          </label>
          <div className="flex items-center gap-2">
            <button type="submit" className={buttonClass}>
              Save
            </button>
            {saved && <span role="status">Saved.</span>}
          </div>
        </form>
      )}
      <div className="flex gap-2">
        <textarea
          aria-label="Ask a question"
          placeholder="Ask about your sources"
          rows={2}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              submit()
            }
          }}
          className="min-w-0 flex-1 resize-none rounded border border-neutral-300 bg-transparent px-2 py-1 dark:border-neutral-700"
        />
        {chat.busy ? (
          <button
            type="button"
            onClick={() => void chat.stop()}
            className="rounded bg-red-600 px-3 text-sm text-white"
          >
            Stop
          </button>
        ) : (
          <button
            type="button"
            onClick={submit}
            disabled={!text.trim()}
            className="rounded bg-blue-600 px-3 text-sm text-white disabled:opacity-50"
          >
            Send
          </button>
        )}
      </div>
      <div className="flex gap-2">
        <button
          type="button"
          className={buttonClass}
          onClick={() => setShowSettings(!showSettings)}
        >
          Chat settings
        </button>
        <button
          type="button"
          className={buttonClass}
          disabled={!chat.messages?.length}
          onClick={() => {
            if (window.confirm('Delete this notebook’s chat history?')) void chat.clear()
          }}
        >
          Clear chat
        </button>
      </div>
    </div>
  )
}
