import { useEffect, useState, type RefObject } from 'react'
import { api, type SearchResult } from '../api'
import { describeLocation } from '../format'

interface SearchBoxProps {
  notebookId: string
  inputRef: RefObject<HTMLInputElement>
  onOpen: (result: SearchResult) => void
}

/** Split `text` around the search terms so matches can be highlighted. */
function highlightTerms(text: string, query: string) {
  const terms = [...new Set(query.toLowerCase().match(/\w+/g) ?? [])]
  if (terms.length === 0) return text
  const pattern = new RegExp(
    `(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`,
    'gi',
  )
  return text.split(pattern).map((part, i) =>
    i % 2 === 1 ? (
      <mark key={i} className="bg-yellow-200 text-inherit dark:bg-yellow-700">
        {part}
      </mark>
    ) : (
      part
    ),
  )
}

export function SearchBox({ notebookId, inputRef, onOpen }: SearchBoxProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const q = query.trim()
    if (!q) return
    let cancelled = false
    const timer = setTimeout(() => {
      api
        .search(notebookId, q)
        .then((r) => {
          if (!cancelled) {
            setResults(r)
            setError(null)
          }
        })
        .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)))
    }, 300)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query, notebookId])

  const open = query.trim() !== '' && (results !== null || error !== null)

  return (
    <div className="relative ml-auto w-72">
      <input
        ref={inputRef}
        type="search"
        aria-label="Search sources"
        placeholder="Search sources (Ctrl+K)"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          if (!e.target.value.trim()) setResults(null)
        }}
        onKeyDown={(e) => {
          if (e.key === 'Escape') {
            setQuery('')
            setResults(null)
          }
        }}
        className="w-full rounded border border-neutral-300 bg-transparent px-2 py-1 dark:border-neutral-700"
      />
      {open && (
        <div
          role="region"
          aria-label="Search results"
          className="absolute right-0 z-30 mt-1 max-h-96 w-[28rem] overflow-auto rounded border border-neutral-300 bg-white shadow dark:border-neutral-700 dark:bg-neutral-900"
        >
          {error && (
            <p role="alert" className="p-3 text-red-600">
              {error}
            </p>
          )}
          {results?.length === 0 && <p className="p-3 text-neutral-500">No matches.</p>}
          <ul>
            {results?.map((r) => (
              <li key={r.chunk_id}>
                <button
                  type="button"
                  onClick={() => {
                    onOpen(r)
                    setQuery('')
                    setResults(null)
                  }}
                  className="block w-full px-3 py-2 text-left text-sm hover:bg-neutral-100 dark:hover:bg-neutral-800"
                >
                  <span className="font-semibold">{r.source_name}</span>
                  {r.kind === 'note' && (
                    <span className="ml-2 rounded bg-neutral-200 px-1 text-xs dark:bg-neutral-800">
                      Note
                    </span>
                  )}
                  {describeLocation(r.location) && (
                    <span className="ml-2 text-xs text-neutral-500">
                      {describeLocation(r.location)}
                    </span>
                  )}
                  <span className="mt-0.5 line-clamp-3 block text-neutral-700 dark:text-neutral-300">
                    {highlightTerms(r.excerpt, query)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
