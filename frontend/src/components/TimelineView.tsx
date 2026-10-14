import type { Citation, TimelineData } from '../api'
import { SourceChips } from './SourceChips'

interface TimelineViewProps {
  data: TimelineData
  citations: Citation[]
  onOpenCitation: (citation: Citation) => void
}

export function TimelineView({ data, citations, onOpenCitation }: TimelineViewProps) {
  return (
    <div className="space-y-6">
      {data.events.length === 0 ? (
        <p className="text-neutral-500">No dated events found</p>
      ) : (
        <ol
          aria-label="Timeline events"
          className="space-y-4 border-l-2 border-neutral-300 pl-4 dark:border-neutral-700"
        >
          {data.events.map((e, i) => (
            <li key={i} className="relative">
              <span
                aria-hidden="true"
                className="absolute -left-[1.4rem] top-1.5 h-2.5 w-2.5 rounded-full bg-blue-600"
              />
              <div className="text-xs font-semibold text-blue-700 dark:text-blue-300">{e.date}</div>
              <div className="font-medium">
                {e.title}
                <SourceChips labels={e.sources} citations={citations} onOpen={onOpenCitation} />
              </div>
              {e.description && (
                <p className="text-neutral-700 dark:text-neutral-300">{e.description}</p>
              )}
            </li>
          ))}
        </ol>
      )}
      {data.cast.length > 0 && (
        <section aria-label="Key people and entities">
          <h3 className="mb-2 text-lg font-semibold">Key people and entities</h3>
          <ul className="space-y-1">
            {data.cast.map((m, i) => (
              <li key={i}>
                <strong>{m.name}</strong>
                {m.role && (
                  <span className="text-neutral-600 dark:text-neutral-400"> — {m.role}</span>
                )}
                <SourceChips labels={m.sources} citations={citations} onOpen={onOpenCitation} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
