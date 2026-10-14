import type { Citation } from '../api'
import { CitationChip } from './CitationChip'

/** Citation chips for a list of passage numbers (the "sources" of a structured item). */
export function SourceChips({
  labels,
  citations,
  onOpen,
}: {
  labels: number[]
  citations: Citation[]
  onOpen: (citation: Citation) => void
}) {
  const byLabel = new Map(citations.map((c) => [c.label, c]))
  return (
    <>
      {labels.map((n) => (
        <CitationChip key={n} label={n} citation={byLabel.get(n)} onOpen={onOpen} />
      ))}
    </>
  )
}
