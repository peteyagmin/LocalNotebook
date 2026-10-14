import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { MindNodeData } from '../api'

const NODE_W = 210
const NODE_H = 44
const GAP_X = 70
const GAP_Y = 18

interface MindNodeProps extends Record<string, unknown> {
  label: string
  path: string[]
  hasChildren: boolean
  collapsed: boolean
  onToggle: () => void
  onAsk: (question: string) => void
}

/** The chat message for a node: "Tell me about {node} in the context of {parent path}" (FR-5.6). */
export function askQuestion(label: string, parentPath: string[]): string {
  return parentPath.length
    ? `Tell me about ${label} in the context of ${parentPath.join(' > ')}`
    : `Tell me about ${label}`
}

function MindNode({ data }: NodeProps<Node<MindNodeProps>>) {
  return (
    <div
      className="flex items-center gap-1 rounded-lg border border-blue-400 bg-blue-50 px-2 text-sm text-neutral-900 dark:bg-blue-950 dark:text-neutral-100"
      style={{ width: NODE_W, height: NODE_H }}
    >
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <button
        type="button"
        className="nodrag nopan min-w-0 flex-1 truncate text-left hover:underline"
        title={data.label}
        aria-label={`Ask about ${data.label}`}
        onClick={() => data.onAsk(askQuestion(data.label, data.path))}
      >
        {data.label}
      </button>
      {data.hasChildren && (
        <button
          type="button"
          className="nodrag nopan rounded px-1.5 text-neutral-600 hover:bg-blue-100 dark:hover:bg-blue-900"
          aria-label={`${data.collapsed ? 'Expand' : 'Collapse'} ${data.label}`}
          aria-expanded={!data.collapsed}
          onClick={data.onToggle}
        >
          {data.collapsed ? '+' : '−'}
        </button>
      )}
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </div>
  )
}

const nodeTypes = { mind: MindNode }

function layout(
  root: MindNodeData,
  collapsed: Set<string>,
  onToggle: (id: string) => void,
  onAsk: (q: string) => void,
) {
  const nodes: Node<MindNodeProps>[] = []
  const edges: Edge[] = []
  let row = 0

  function place(node: MindNodeData, id: string, depth: number, path: string[]): number {
    const isCollapsed = collapsed.has(id)
    const visibleChildren = isCollapsed ? [] : node.children
    const childYs = visibleChildren.map((c, i) => {
      const childId = `${id}.${i}`
      edges.push({ id: `${id}->${childId}`, source: id, target: childId, type: 'smoothstep' })
      return place(c, childId, depth + 1, [...path, node.label])
    })
    let y: number
    if (childYs.length === 0) {
      y = row * (NODE_H + GAP_Y)
      row += 1
    } else {
      y = (childYs[0] + childYs[childYs.length - 1]) / 2
    }
    nodes.push({
      id,
      type: 'mind',
      position: { x: depth * (NODE_W + GAP_X), y },
      initialWidth: NODE_W,
      initialHeight: NODE_H,
      draggable: false,
      data: {
        label: node.label,
        path,
        hasChildren: node.children.length > 0,
        collapsed: isCollapsed,
        onToggle: () => onToggle(id),
        onAsk,
      },
    })
    return y
  }

  place(root, 'r', 0, [])
  return { nodes, edges }
}

function Graph({ root, onAsk }: { root: MindNodeData; onAsk: (q: string) => void }) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const { fitView } = useReactFlow()
  const box = useRef<HTMLDivElement>(null)
  const { nodes, edges } = useMemo(
    () =>
      layout(
        root,
        collapsed,
        (id) =>
          setCollapsed((c) => {
            const next = new Set(c)
            if (next.has(id)) next.delete(id)
            else next.add(id)
            return next
          }),
        onAsk,
      ),
    [root, collapsed, onAsk],
  )

  useEffect(() => {
    const t = setTimeout(() => void fitView({ duration: 200, padding: 0.15 }), 50)
    return () => clearTimeout(t)
  }, [nodes.length, fitView])

  // Re-fit when the pane is resized (Expand / Shrink, dragging the pane divider).
  useEffect(() => {
    const el = box.current
    if (!el) return
    let timer: ReturnType<typeof setTimeout> | undefined
    const observer = new ResizeObserver(() => {
      clearTimeout(timer)
      timer = setTimeout(() => void fitView({ duration: 150, padding: 0.15 }), 80)
    })
    observer.observe(el)
    return () => {
      observer.disconnect()
      clearTimeout(timer)
    }
  }, [fitView])

  return (
    <div ref={box} className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.2}
        nodesDraggable={false}
        nodesConnectable={false}
      >
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  )
}

interface MindMapViewProps {
  root: MindNodeData
  /** Called with the question to send to the chat when a node is clicked. */
  onAsk: (question: string) => void
}

export function MindMapView({ root, onAsk }: MindMapViewProps) {
  return (
    <div role="group" aria-label="Mind map" className="h-full min-h-[360px] w-full">
      <ReactFlowProvider>
        <Graph root={root} onAsk={onAsk} />
      </ReactFlowProvider>
    </div>
  )
}
