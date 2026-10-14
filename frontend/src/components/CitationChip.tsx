import type { Citation } from '../api'
import { describeLocation } from '../format'

interface CitationChipProps {
  label: number
  citation?: Citation
  onOpen: (citation: Citation) => void
}

/** Numbered chip; hover or focus shows the source name and an excerpt (FR-3.2). */
export function CitationChip({ label, citation, onOpen }: CitationChipProps) {
  if (!citation) return <span>[{label}]</span>
  const removed = citation.removed === true
  return (
    <span className="group relative mx-0.5 inline-block align-baseline">
      <button
        type="button"
        disabled={removed}
        onClick={() => onOpen(citation)}
        aria-label={
          removed
            ? `Citation ${label}: source removed`
            : `Citation ${label}: ${citation.source_name}`
        }
        className={`rounded-full px-1.5 text-xs leading-5 ${
          removed
            ? 'bg-neutral-200 text-neutral-500 line-through dark:bg-neutral-800'
            : 'bg-blue-100 text-blue-800 hover:bg-blue-200 dark:bg-blue-900 dark:text-blue-100'
        }`}
      >
        {label}
      </button>
      <span
        role="tooltip"
        className="invisible absolute bottom-full left-0 z-20 mb-1 w-64 rounded border border-neutral-300 bg-white p-2 text-xs font-normal text-neutral-800 shadow group-focus-within:visible group-hover:visible dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
      >
        <strong className="block">
          {removed ? 'Source removed' : citation.source_name}
          {!removed && describeLocation(citation.location) && (
            <span className="ml-2 font-normal text-neutral-500">
              {describeLocation(citation.location)}
            </span>
          )}
        </strong>
        <span className="line-clamp-4">{citation.excerpt}</span>
      </span>
    </span>
  )
}
