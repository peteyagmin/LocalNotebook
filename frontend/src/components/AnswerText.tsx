import Markdown, { defaultUrlTransform } from 'react-markdown'
import type { Citation } from '../api'
import { CitationChip } from './CitationChip'

interface AnswerTextProps {
  text: string
  citations: Citation[]
  onOpenCitation: (citation: Citation) => void
}

const CITE = /\[(\d+)\]/g

/** Sanitized Markdown (no raw HTML, no images) with [n] markers rendered as citation chips. */
export function AnswerText({ text, citations, onOpenCitation }: AnswerTextProps) {
  const byLabel = new Map(citations.map((c) => [c.label, c]))
  const source = text.replace(CITE, '[$1](cite:$1)')
  return (
    <div
      className={
        'space-y-2 [&_blockquote]:border-l-4 [&_blockquote]:border-neutral-300 [&_blockquote]:pl-3 ' +
        '[&_blockquote]:italic [&_h1]:text-xl [&_h1]:font-semibold [&_h2]:text-lg [&_h2]:font-semibold ' +
        '[&_h3]:font-semibold [&_li]:ml-5 [&_ol]:list-decimal [&_ul]:list-disc'
      }
    >
      <Markdown
        skipHtml
        urlTransform={(url) => (url.startsWith('cite:') ? url : defaultUrlTransform(url))}
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith('cite:')) {
              const label = Number(href.slice(5))
              return (
                <CitationChip label={label} citation={byLabel.get(label)} onOpen={onOpenCitation} />
              )
            }
            return (
              <a href={href} target="_blank" rel="noreferrer noopener" className="underline">
                {children}
              </a>
            )
          },
          img: () => null,
        }}
      >
        {source}
      </Markdown>
    </div>
  )
}
