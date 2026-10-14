import { useCallback, useState } from 'react'
import type { Source } from '../api'
import { ChatPane } from '../components/ChatPane'
import { Pane } from '../components/Pane'
import { Resizer } from '../components/Resizer'
import { ArtifactView } from '../components/ArtifactView'
import { NoteEditor } from '../components/NoteEditor'
import { SourcesPane } from '../components/SourcesPane'
import { StudioPane } from '../components/StudioPane'
import type { StudioTarget } from '../components/studio'
import { SourceViewer, type ViewTarget } from '../components/SourceViewer'
import { useEscape } from '../hooks/useEscape'
import { useArtifacts } from '../hooks/useArtifacts'
import { useNotes } from '../hooks/useNotes'
import { useSources } from '../hooks/useSources'

interface WorkspaceProps {
  notebookId: string
  viewing: ViewTarget | null
  onView: (target: ViewTarget | null) => void
  studio: StudioTarget | null
  onStudio: (target: StudioTarget | null) => void
}

export function Workspace({ notebookId, viewing, onView, studio, onStudio }: WorkspaceProps) {
  const { artifacts, refresh: refreshArtifacts } = useArtifacts(notebookId)
  const { notes, refresh: refreshNotes } = useNotes(notebookId)
  const [expanded, setExpanded] = useState(false)
  const [askRequest, setAskRequest] = useState<{ id: number; text: string } | null>(null)
  const { sources, setSources, refresh, error } = useSources(notebookId)
  const closeViewer = useCallback(() => onView(null), [onView])
  const viewed: Source | undefined = sources?.find((s) => s.id === viewing?.sourceId)
  const artifactVersion = (artifacts ?? [])
    .map((a) => `${a.id}:${a.state}:${a.updated_at}`)
    .join(',')
  const openCitation = (c: {
    source_id: string
    location: { char_start: number; char_end: number }
  }) =>
    onView({
      sourceId: c.source_id,
      highlight: { start: c.location.char_start, end: c.location.char_end },
    })
  const closeStudio = () => {
    setExpanded(false)
    onStudio(null)
  }
  useEscape(closeStudio, studio !== null)
  const detail = studio ? (
    studio.type === 'artifact' ? (
      <ArtifactView
        key={studio.id}
        notebookId={notebookId}
        artifactId={studio.id}
        version={artifactVersion}
        expanded={expanded}
        onToggleExpand={() => setExpanded(!expanded)}
        onClose={closeStudio}
        onOpenCitation={openCitation}
        onAskChat={(text) => {
          setExpanded(false) // make the chat visible
          setAskRequest({ id: Date.now(), text })
        }}
        onChanged={() => void refreshArtifacts()}
      />
    ) : (
      <NoteEditor
        key={studio.id}
        notebookId={notebookId}
        noteId={studio.id}
        expanded={expanded}
        onToggleExpand={() => setExpanded(!expanded)}
        onClose={closeStudio}
        onOpenCitation={openCitation}
        onChanged={() => void refreshNotes()}
      />
    )
  ) : null
  const sourcesKey = (sources ?? [])
    .filter((s) => s.enabled && s.state === 'ready')
    .map((s) => s.id)
    .join(',')
  const [left, setLeft] = useState({ width: 280, collapsed: false })
  const [right, setRight] = useState({ width: 320, collapsed: false })

  return (
    <div className="relative flex min-h-0 flex-1">
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
        askRequest={askRequest}
        sourcesKey={sourcesKey}
        onNoteSaved={(note) => {
          void refreshNotes()
          onStudio({ type: 'note', id: note.id })
        }}
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
        <StudioPane
          notebookId={notebookId}
          artifacts={artifacts}
          notes={notes}
          refreshArtifacts={refreshArtifacts}
          refreshNotes={refreshNotes}
          refreshSources={refresh}
          onOpen={onStudio}
        />
      </Pane>
      {studio && (
        // One element for both sizes, so expanding does not reload the editor or artifact.
        <div
          className="absolute inset-y-0 right-0 z-20 border-l border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-950"
          style={expanded ? { left: 0 } : { width: right.collapsed ? 320 : right.width }}
        >
          {detail}
        </div>
      )}
    </div>
  )
}
