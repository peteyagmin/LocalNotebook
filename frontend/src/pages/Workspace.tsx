import { useCallback, useState } from 'react'
import type { Source } from '../api'
import { SourceViewer } from '../components/SourceViewer'
import { SourcesPane } from '../components/SourcesPane'
import { useSources } from '../hooks/useSources'
import { Pane } from '../components/Pane'
import { Resizer } from '../components/Resizer'

export function Workspace({ notebookId }: { notebookId: string }) {
  const { sources, setSources, refresh, error } = useSources(notebookId)
  const [viewing, setViewing] = useState<string | null>(null)
  const closeViewer = useCallback(() => setViewing(null), [])
  const viewed: Source | undefined = sources?.find((s) => s.id === viewing)
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
          onOpen={(s) => setViewing(s.id)}
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
      <Pane
        title="Chat"
        side="center"
        collapsed={false}
        onToggle={() => {}}
        overlay={
          viewed && <SourceViewer notebookId={notebookId} source={viewed} onClose={closeViewer} />
        }
      >
        <p className="text-neutral-500">Nothing here yet.</p>
      </Pane>
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
