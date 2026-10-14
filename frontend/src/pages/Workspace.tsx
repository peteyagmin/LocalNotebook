import { useCallback, useState } from 'react'
import type { Source } from '../api'
import { ChatPane } from '../components/ChatPane'
import { Pane } from '../components/Pane'
import { Resizer } from '../components/Resizer'
import { SourcesPane } from '../components/SourcesPane'
import { SourceViewer, type ViewTarget } from '../components/SourceViewer'
import { useSources } from '../hooks/useSources'

interface WorkspaceProps {
  notebookId: string
  viewing: ViewTarget | null
  onView: (target: ViewTarget | null) => void
}

export function Workspace({ notebookId, viewing, onView }: WorkspaceProps) {
  const { sources, setSources, refresh, error } = useSources(notebookId)
  const closeViewer = useCallback(() => onView(null), [onView])
  const viewed: Source | undefined = sources?.find((s) => s.id === viewing?.sourceId)
  const sourcesKey = (sources ?? [])
    .filter((s) => s.enabled && s.state === 'ready')
    .map((s) => s.id)
    .join(',')
  const [left, setLeft] = useState({ width: 280, collapsed: false })
  const [right, setRight] = useState({ width: 320, collapsed: false })

  return (
    <div className="flex min-h-0 flex-1">
      <Pane
        title="Sources"
        side="left"
        width={left.width}
        collapsed={left.collapsed}
        onToggle={() => setLeft({ ...left, collapsed: !left.collapsed })}
      >
        {error && (
          <p role="alert" className="text-red-600">
            {error}
          </p>
        )}
        <SourcesPane
          notebookId={notebookId}
          sources={sources}
          setSources={setSources}
          refresh={refresh}
          onOpen={(s) => onView({ sourceId: s.id })}
        />
      </Pane>
      {!left.collapsed && (
        <Resizer
          label="Resize Sources pane"
          value={left.width}
          min={200}
          max={560}
          direction={1}
          onChange={(width) => setLeft({ ...left, width })}
        />
      )}
      <ChatPane
        notebookId={notebookId}
        sourcesKey={sourcesKey}
        onOpenCitation={(c) =>
          onView({
            sourceId: c.source_id,
            highlight: { start: c.location.char_start, end: c.location.char_end },
          })
        }
        overlay={
          viewed && (
            <SourceViewer
              notebookId={notebookId}
              source={viewed}
              highlight={viewing?.highlight}
              onClose={closeViewer}
            />
          )
        }
      />
      {!right.collapsed && (
        <Resizer
          label="Resize Studio pane"
          value={right.width}
          min={240}
          max={640}
          direction={-1}
          onChange={(width) => setRight({ ...right, width })}
        />
      )}
      <Pane
        title="Studio"
        side="right"
        width={right.width}
        collapsed={right.collapsed}
        onToggle={() => setRight({ ...right, collapsed: !right.collapsed })}
      >
        <p className="text-neutral-500">Nothing here yet.</p>
      </Pane>
    </div>
  )
}
