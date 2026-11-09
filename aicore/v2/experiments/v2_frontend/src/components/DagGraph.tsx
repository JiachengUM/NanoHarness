import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import {
  Background,
  BaseEdge,
  Controls,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  getSmoothStepPath,
  useReactFlow,
  type EdgeProps,
  type EdgeTypes,
  type NodeProps,
  type NodeTypes,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { DiagnosisDecision, DiagnosisSource } from '../domain/planEvents'
import { asRecord, formatDetailValue } from '../utils/unknown'
import {
  createDagSeedLayout,
  createDagStructureKey,
  createDagViewportKey,
  layoutDagWithElk,
  refreshDagLayoutData,
} from './dagLayout'
import type {
  DagEdgeData,
  DagFlowEdge,
  DagFlowLayout,
  DagFlowNode,
  DagNodeData,
  DagStateEdge,
  DagStateNode,
} from './dagTypes'

interface DagGraphProps {
  nodes: DagStateNode[]
  edges: DagStateEdge[]
  goal?: string
  selectedDetailNodeId?: string
  onSelectedDetailNodeIdChange: (nodeId: string | undefined) => void
}

export const DIAGNOSIS_SOURCE_LABELS: Record<DiagnosisSource, string> = {
  rule: 'Rule',
  llm: 'LLM',
  fallback: 'Fallback',
}

export const DIAGNOSIS_OUTCOME_LABELS: Record<DiagnosisDecision['outcome'], string> = {
  replan: '需要重规划',
  skip_unsolvable: '无法完成',
  accept_degraded: '降级接受',
}

function statusLabel(status: string): string {
  switch (status) {
    case 'running': return '执行中'
    case 'diagnosing': return '诊断中'
    case 'needs_replan': return '需要重规划'
    case 'success': return '完成'
    case 'degraded': return '降级完成'
    case 'unsolvable': return '无法完成'
    case 'skipped': return '跳过'
    case 'failed': return '失败'
    default: return '等待'
  }
}

function truncateDagDisplayText(value: string | undefined, maxChars = 18): string {
  const text = value?.trim() ?? ''
  const chars = Array.from(text)
  return chars.length > maxChars ? `${chars.slice(0, maxChars).join('')}...` : text
}

function successCheckResult(node: Exclude<DagNodeData, { isGoalRoot: true }>): string {
  if (node.status === 'skipped') return '未执行'
  if (node.status === 'diagnosing') return '诊断中'
  if (node.status === 'needs_replan') return '未通过'
  if (node.unmet !== undefined || node.runnerErrors.length > 0) return '未通过'
  if (node.status === 'success' && node.processError === undefined) return '通过'
  if (node.status === 'failed' || node.status === 'unsolvable') return '未通过'
  return '无明确结果'
}

function stopDagControlPointer(event: ReactPointerEvent<HTMLElement>) {
  event.stopPropagation()
}

export function DagNodeCard({
  node,
  isDetailSelected = false,
  onToggleDetail,
}: {
  node: DagNodeData
  isDetailSelected?: boolean
  onToggleDetail?: (node: DagNodeData) => void
}) {
  const toggleDetail = (event: ReactMouseEvent<HTMLButtonElement>) => {
    event.stopPropagation()
    onToggleDetail?.(node)
  }

  if (node.isGoalRoot) {
    return (
      <article aria-label={`用户目标 ${node.goal}`} className="dag-goal-card" title={node.goal}>
        <button
          aria-expanded={isDetailSelected}
          className="dag-goal-summary nodrag nopan nowheel"
          type="button"
          onClick={toggleDetail}
          onPointerDown={stopDagControlPointer}
        >
          <span className="dag-goal-copy">
            <span className="dag-goal-label">用户目标</span>
            <strong>{truncateDagDisplayText(node.goal, 15)}</strong>
          </span>
          <span className="dag-detail-chip">{isDetailSelected ? '收起' : '详情'}</span>
        </button>
      </article>
    )
  }

  const outputSpec = asRecord(node.outputSpec)
  return (
    <article
      aria-label={`节点 ${node.stepId}，目标 ${node.stepGoal}，状态 ${statusLabel(node.status)}`}
      className={`dag-node-card node-${node.status}${node.isStandalone ? ' dag-node-standalone' : ''}`}
    >
      <div className="dag-node-top">
        <span className="dag-step-label">{node.stepId}</span>
        <span className="dag-node-state">
          <span className="dag-status-pulse" aria-hidden="true" />
          {statusLabel(node.status)}
        </span>
      </div>
      <dl className="dag-task-fields dag-node-summary-fields">
        <div>
          <dt>步骤目标</dt>
          <dd title={node.stepGoal}>{truncateDagDisplayText(node.stepGoal, 34)}</dd>
        </div>
        <div><dt>调用工具</dt><dd>{node.op}</dd></div>
      </dl>
      <div className="dag-node-tags">
        {node.condition && <span>条件步骤</span>}
        {outputSpec.is_list === true && <span>列表输出</span>}
        {node.unmet !== undefined && <span>未完全达成</span>}
        {node.diagnosis?.status === 'completed' && (
          <span className="dag-diagnosis-tag">
            {DIAGNOSIS_SOURCE_LABELS[node.diagnosis.source]}
            {' · '}
            {DIAGNOSIS_OUTCOME_LABELS[node.diagnosis.decision.outcome]}
          </span>
        )}
      </div>
      <button
        aria-expanded={isDetailSelected}
        className="dag-detail-toggle nodrag nopan nowheel"
        type="button"
        onClick={toggleDetail}
        onPointerDown={stopDagControlPointer}
      >
        {isDetailSelected ? '收起' : '详情'}
      </button>
    </article>
  )
}

function DagNode({ data }: NodeProps<DagFlowNode>) {
  const node = data as DagNodeData
  return (
    <>
      <Handle className="dag-node-handle" type="target" position={Position.Top} isConnectable={false} />
      <DagNodeCard
        node={node}
        isDetailSelected={Boolean(node.isDetailSelected)}
        onToggleDetail={node.onToggleDetail}
      />
      <Handle className="dag-node-handle" type="source" position={Position.Bottom} isConnectable={false} />
    </>
  )
}

export function DagNodeDetailPanel({
  node,
  onClose,
}: {
  node: DagNodeData
  onClose: () => void
}) {
  if (node.isGoalRoot) {
    return (
      <aside className="dag-graph-detail-panel" aria-label="用户目标详情">
        <header className="dag-graph-detail-header">
          <h3>用户目标</h3>
          <button className="dag-graph-detail-close nodrag nopan nowheel" type="button" onClick={onClose}>收起</button>
        </header>
        <p className="dag-graph-detail-goal">{node.goal}</p>
      </aside>
    )
  }

  const diagnosis = node.diagnosis
  const diagnosisElapsedMs = diagnosis?.status === 'completed'
    ? Date.parse(diagnosis.completedAt) - Date.parse(diagnosis.startedAt)
    : undefined

  return (
    <aside className="dag-graph-detail-panel" aria-label={`${node.stepId} 详情`}>
      <header className="dag-graph-detail-header">
        <h3>{node.stepId} 详情</h3>
        <button className="dag-graph-detail-close nodrag nopan nowheel" type="button" onClick={onClose}>收起</button>
      </header>
      <dl className="dag-detail-fields dag-graph-detail-fields">
        <div><dt>Step ID</dt><dd>{node.stepId}</dd></div>
        <div><dt>步骤状态</dt><dd>{statusLabel(node.status)}</dd></div>
        <div><dt>步骤目标</dt><dd>{node.stepGoal}</dd></div>
        <div><dt>调用工具</dt><dd>{node.op}</dd></div>
        <div><dt>依赖步骤</dt><dd><pre className="dag-detail-json">{formatDetailValue(node.dependsOn)}</pre></dd></div>
        <div><dt>执行条件</dt><dd>{node.condition ?? '无'}</dd></div>
        <div><dt>成功检查</dt><dd><pre className="dag-detail-json">{node.successCheck}</pre></dd></div>
        <div><dt>检查结论</dt><dd>{successCheckResult(node)}</dd></div>
        <div><dt>输出定义</dt><dd><pre className="dag-detail-json">{formatDetailValue(node.outputSpec)}</pre></dd></div>
        <div><dt>Plan 原始输入</dt><dd><pre className="dag-detail-json">{formatDetailValue(node.rawInputs)}</pre></dd></div>
        <div><dt>实际工具输入</dt><dd><pre className="dag-detail-json">{formatDetailValue(node.resolvedInputs)}</pre></dd></div>
        <div><dt>工具原始结果</dt><dd><pre className="dag-detail-json">{formatDetailValue(node.toolOutput)}</pre></dd></div>
        <div><dt>Concept 输出</dt><dd><pre className="dag-detail-json">{formatDetailValue(node.conceptOutput)}</pre></dd></div>
        <div><dt>过程错误</dt><dd><pre className="dag-detail-json">{formatDetailValue(node.processError)}</pre></dd></div>
        <div><dt>未达成诊断</dt><dd><pre className="dag-detail-json">{formatDetailValue(node.unmet)}</pre></dd></div>
        <div><dt>Runner 错误</dt><dd><pre className="dag-detail-json">{formatDetailValue(node.runnerErrors)}</pre></dd></div>
        <div><dt>跳过原因</dt><dd>{node.skipReason ?? '无'}</dd></div>
        <div><dt>开始时间</dt><dd>{node.startedAt ?? '未开始'}</dd></div>
        <div><dt>完成时间</dt><dd>{node.completedAt ?? '未完成'}</dd></div>
      </dl>
      {diagnosis && (
        <section className="dag-diagnosis-trace" aria-label="补救诊断">
          <h4>补救诊断</h4>
          <dl className="dag-detail-fields">
            <div><dt>当前状态</dt><dd>{diagnosis.status === 'running' ? '诊断中' : '已完成'}</dd></div>
            <div><dt>成功检查</dt><dd><pre className="dag-detail-json">{diagnosis.successCheck}</pre></dd></div>
            <div><dt>失败信息</dt><dd>{diagnosis.failureMessage}</dd></div>
            {diagnosis.processErrorKind && (
              <div><dt>错误类型</dt><dd>{diagnosis.processErrorKind}</dd></div>
            )}
            {diagnosis.status === 'completed' && (
              <>
                <div><dt>诊断来源</dt><dd>{DIAGNOSIS_SOURCE_LABELS[diagnosis.source]}</dd></div>
                <div><dt>最终裁决</dt><dd>{DIAGNOSIS_OUTCOME_LABELS[diagnosis.decision.outcome]}</dd></div>
                {diagnosis.decision.outcome === 'replan' && (
                  <>
                    <div><dt>失败假设</dt><dd>{diagnosis.decision.failedAssumption}</dd></div>
                    <div><dt>重试方向</dt><dd>{diagnosis.decision.retryDirection}</dd></div>
                  </>
                )}
                {diagnosis.decision.outcome === 'skip_unsolvable' && (
                  <div><dt>无法完成原因</dt><dd>{diagnosis.decision.unsolvableReason}</dd></div>
                )}
                {diagnosis.decision.outcome === 'accept_degraded' && (
                  <div><dt>降级限制</dt><dd>{diagnosis.decision.limitation}</dd></div>
                )}
              </>
            )}
            <div><dt>开始时间</dt><dd>{diagnosis.startedAt}</dd></div>
            {diagnosis.status === 'completed' && (
              <>
                <div><dt>完成时间</dt><dd>{diagnosis.completedAt}</dd></div>
                {Number.isFinite(diagnosisElapsedMs) && (
                  <div><dt>诊断耗时</dt><dd>{diagnosisElapsedMs} ms</dd></div>
                )}
              </>
            )}
          </dl>
        </section>
      )}
    </aside>
  )
}

function DagEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  data,
}: EdgeProps<DagFlowEdge>) {
  const [edgePath] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 18,
  })
  const edgeData = data as DagEdgeData | undefined
  const status = edgeData?.status ?? 'pending'
  const relation = edgeData?.relation ?? 'dependency'
  if (relation === 'goal') {
    return <BaseEdge id={id} path={edgePath} className="dag-flow-edge-goal" />
  }

  return (
    <>
      <BaseEdge
        id={`${id}-base`}
        path={edgePath}
        markerEnd={markerEnd}
        className={`dag-flow-edge-base edge-${status}`}
      />
      {status === 'running' && (
        <BaseEdge
          id={id}
          path={edgePath}
          className="dag-flow-edge-animated edge-running"
        />
      )}
    </>
  )
}

const nodeTypes: NodeTypes = { dagNode: DagNode }
const edgeTypes: EdgeTypes = { dagEdge: DagEdge }

function DagViewportAutoFit({ viewportKey }: { viewportKey: string }) {
  const { fitView } = useReactFlow()

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      void fitView({ padding: 0.18 })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [fitView, viewportKey])

  return null
}

function DagGraphInner({
  nodes,
  edges,
  goal,
  selectedDetailNodeId,
  onSelectedDetailNodeIdChange,
}: DagGraphProps) {
  const [layout, setLayout] = useState<DagFlowLayout>(
    () => createDagSeedLayout(nodes, edges, goal),
  )
  const latestDagDataRef = useRef({ nodes, edges, goal })
  const structureKey = useMemo(
    () => createDagStructureKey(nodes, edges, goal),
    [edges, goal, nodes],
  )

  useLayoutEffect(() => {
    latestDagDataRef.current = { nodes, edges, goal }
  }, [edges, goal, nodes])

  useEffect(() => {
    let cancelled = false
    const current = latestDagDataRef.current
    setLayout(createDagSeedLayout(current.nodes, current.edges, current.goal))
    void layoutDagWithElk(current.nodes, current.edges, current.goal).then((nextLayout) => {
      if (cancelled) return
      const latest = latestDagDataRef.current
      setLayout(refreshDagLayoutData(
        nextLayout,
        latest.nodes,
        latest.edges,
        latest.goal,
      ))
    })
    return () => { cancelled = true }
  }, [structureKey])

  useEffect(() => {
    setLayout((current) => refreshDagLayoutData(current, nodes, edges, goal))
  }, [edges, goal, nodes])

  const hasNodes = layout.nodes.length > 0
  const proOptions = useMemo(() => ({ hideAttribution: true }), [])
  const viewportKey = useMemo(() => createDagViewportKey(layout), [layout])
  const toggleDetailNode = useCallback((node: DagNodeData) => {
    onSelectedDetailNodeIdChange(
      selectedDetailNodeId === node.id ? undefined : node.id,
    )
  }, [onSelectedDetailNodeIdChange, selectedDetailNodeId])
  const selectedDetailNode = useMemo(
    () => layout.nodes.find((node) => node.id === selectedDetailNodeId)?.data,
    [layout.nodes, selectedDetailNodeId],
  )
  const flowNodes = useMemo(
    () => layout.nodes.map((node) => ({
      ...node,
      data: {
        ...node.data,
        isDetailSelected: node.id === selectedDetailNodeId,
        onToggleDetail: toggleDetailNode,
      },
    })),
    [layout.nodes, selectedDetailNodeId, toggleDetailNode],
  )

  useEffect(() => {
    if (!selectedDetailNodeId) return
    if (layout.nodes.some((node) => node.id === selectedDetailNodeId)) return
    onSelectedDetailNodeIdChange(undefined)
  }, [layout.nodes, onSelectedDetailNodeIdChange, selectedDetailNodeId])

  if (!hasNodes) {
    return <div className="empty-copy dag-empty">等待 Plan DAG</div>
  }

  return (
    <div className="dag-flow-shell">
      <ReactFlow
        key={viewportKey}
        nodes={flowNodes}
        edges={layout.edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnScroll
        fitView
        fitViewOptions={{ padding: 0.18 }}
        proOptions={proOptions}
      >
        <Background gap={24} color="#dfe7ee" />
        <Controls showInteractive={false} />
        <DagViewportAutoFit viewportKey={viewportKey} />
      </ReactFlow>
      {selectedDetailNode && (
        <DagNodeDetailPanel
          node={selectedDetailNode}
          onClose={() => onSelectedDetailNodeIdChange(undefined)}
        />
      )}
    </div>
  )
}

export function DagGraph(props: DagGraphProps) {
  return (
    <ReactFlowProvider>
      <DagGraphInner {...props} />
    </ReactFlowProvider>
  )
}
