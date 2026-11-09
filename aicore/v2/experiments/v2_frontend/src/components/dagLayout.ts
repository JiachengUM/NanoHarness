import { MarkerType } from '@xyflow/react'
import ELK, { type ElkExtendedEdge, type ElkNode } from 'elkjs/lib/elk.bundled.js'
import type { PlanDagNodeStatus } from '../app/planDagReducer'
import type {
  DagFlowEdge,
  DagFlowLayout,
  DagFlowNode,
  DagStateEdge,
  DagStateNode,
} from './dagTypes'

export const DAG_GOAL_NODE_ID = '__dag_goal__'

const NODE_WIDTH = 264
const NODE_HEIGHT = 152
const GOAL_NODE_WIDTH = 260
const GOAL_NODE_HEIGHT = 76
const elk = new ELK()

function seedPosition(index: number): { x: number; y: number } {
  return {
    x: 18 + (index % 3) * 118,
    y: 22 + Math.floor(index / 3) * 58,
  }
}

export function createDagViewportKey(layout: DagFlowLayout): string {
  const nodeKey = layout.nodes
    .map((node) => `${node.id}:${Math.round(node.position.x)}:${Math.round(node.position.y)}`)
    .sort()
    .join('|')
  const edgeKey = layout.edges
    .map((edge) => `${edge.id}:${edge.source}:${edge.target}`)
    .sort()
    .join('|')
  return `${nodeKey}::${edgeKey}`
}

export function createDagStructureKey(
  nodes: DagStateNode[],
  edges: DagStateEdge[],
  goal?: string,
): string {
  const edgePairs = edges
    .map((edge) => [edge.from, edge.to] as const)
    .sort(([leftFrom, leftTo], [rightFrom, rightTo]) =>
      leftFrom.localeCompare(rightFrom) || leftTo.localeCompare(rightTo),
  )
  return JSON.stringify([
    Boolean(rootGoalForLayout(goal, nodes)),
    nodes.map((node) => node.id).sort(),
    edgePairs,
  ])
}

function edgeStatus(
  sourceStatus: PlanDagNodeStatus,
  targetStatus: PlanDagNodeStatus,
): PlanDagNodeStatus {
  if (
    ['diagnosing', 'needs_replan'].includes(sourceStatus)
    || ['diagnosing', 'needs_replan'].includes(targetStatus)
  ) {
    return 'pending'
  }
  if (sourceStatus === 'running' || targetStatus === 'running') return 'running'
  if (
    ['failed', 'unsolvable'].includes(sourceStatus)
    || ['failed', 'unsolvable'].includes(targetStatus)
  ) {
    return 'failed'
  }
  if (sourceStatus === 'skipped' || targetStatus === 'skipped') return 'skipped'
  if (
    ['success', 'degraded'].includes(sourceStatus)
    && ['success', 'degraded'].includes(targetStatus)
  ) {
    return sourceStatus === 'degraded' || targetStatus === 'degraded'
      ? 'degraded'
      : 'success'
  }
  return 'pending'
}

function realIncidentNodeIds(nodes: DagStateNode[], edges: DagStateEdge[]): Set<string> {
  const nodeIds = new Set(nodes.map((node) => node.id))
  const incidentIds = new Set<string>()
  edges.forEach((edge) => {
    if (!nodeIds.has(edge.from) || !nodeIds.has(edge.to)) return
    incidentIds.add(edge.from)
    incidentIds.add(edge.to)
  })
  return incidentIds
}

function entryNodeIds(nodes: DagStateNode[], edges: DagStateEdge[]): string[] {
  const nodeIds = new Set(nodes.map((node) => node.id))
  const targets = new Set<string>()
  edges.forEach((edge) => {
    if (!nodeIds.has(edge.from) || !nodeIds.has(edge.to)) return
    targets.add(edge.to)
  })
  return nodes.filter((node) => !targets.has(node.id)).map((node) => node.id)
}

function rootGoalForLayout(goal: string | undefined, nodes: DagStateNode[]): string | undefined {
  const rootGoal = goal?.trim()
  return rootGoal && nodes.length > 0 ? rootGoal : undefined
}

function goalEdgesFor(
  rootGoal: string | undefined,
  nodes: DagStateNode[],
  edges: DagStateEdge[],
): DagStateEdge[] {
  if (!rootGoal) return []
  return entryNodeIds(nodes, edges).map((nodeId) => ({
    from: DAG_GOAL_NODE_ID,
    to: nodeId,
  }))
}

function goalFlowNode(goal: string, x: number, y: number): DagFlowNode {
  return {
    id: DAG_GOAL_NODE_ID,
    type: 'dagNode',
    position: { x, y },
    data: {
      id: DAG_GOAL_NODE_ID,
      goal,
      status: 'goal',
      isStandalone: false,
      isGoalRoot: true,
    },
    className: 'dag-flow-node-goal',
    draggable: false,
    selectable: false,
    style: { pointerEvents: 'all' },
  }
}

function toFlowNode(
  node: DagStateNode,
  options: { x: number; y: number; isStandalone: boolean },
): DagFlowNode {
  return {
    id: node.id,
    type: 'dagNode',
    position: { x: options.x, y: options.y },
    data: {
      ...node,
      isStandalone: options.isStandalone,
    },
    className: 'dag-flow-node-task',
    draggable: false,
    selectable: false,
    style: { pointerEvents: 'all' },
  }
}

function toFlowEdges(
  edges: DagStateEdge[],
  availableNodeIds: Set<string>,
  statusById: Map<string, PlanDagNodeStatus>,
): DagFlowEdge[] {
  return edges.flatMap((edge): DagFlowEdge[] => {
    if (!availableNodeIds.has(edge.from) || !availableNodeIds.has(edge.to)) return []
    const isGoalRelation = edge.from === DAG_GOAL_NODE_ID
    const status = isGoalRelation
      ? 'goal'
      : edgeStatus(
          statusById.get(edge.from) ?? 'pending',
          statusById.get(edge.to) ?? 'pending',
        )
    return [{
      id: `${edge.from}-${edge.to}`,
      type: 'dagEdge',
      source: edge.from,
      target: edge.to,
      animated: !isGoalRelation && status === 'running',
      data: {
        status,
        relation: isGoalRelation ? 'goal' : 'dependency',
      },
      markerEnd: isGoalRelation
        ? undefined
        : { type: MarkerType.ArrowClosed },
      selectable: false,
    }]
  })
}

export function createDagSeedLayout(
  nodes: DagStateNode[],
  edges: DagStateEdge[],
  goal?: string,
): DagFlowLayout {
  const rootGoal = rootGoalForLayout(goal, nodes)
  const incidentIds = realIncidentNodeIds(nodes, edges)
  const flowNodes = nodes.map((node, index) => {
    const position = seedPosition(index)
    return toFlowNode(node, {
      x: position.x,
      y: position.y,
      isStandalone: !incidentIds.has(node.id),
    })
  })
  const fullFlowNodes = rootGoal
    ? [
        goalFlowNode(rootGoal, 18, 18),
        ...flowNodes.map((node) => ({
          ...node,
          position: {
            x: node.position.x,
            y: node.position.y + GOAL_NODE_HEIGHT + 42,
          },
        })),
      ]
    : flowNodes
  const statusById = new Map<string, PlanDagNodeStatus>(
    nodes.map((node) => [node.id, node.status]),
  )
  const goalEdges = goalEdgesFor(rootGoal, nodes, edges)
  const availableNodeIds = new Set(fullFlowNodes.map((node) => node.id))
  return {
    nodes: fullFlowNodes,
    edges: toFlowEdges([...goalEdges, ...edges], availableNodeIds, statusById),
  }
}

export function refreshDagLayoutData(
  layout: DagFlowLayout,
  nodes: DagStateNode[],
  edges: DagStateEdge[],
  goal?: string,
): DagFlowLayout {
  const nextLayout = createDagSeedLayout(nodes, edges, goal)
  const positionById = new Map(
    layout.nodes.map((node) => [node.id, node.position]),
  )
  return {
    nodes: nextLayout.nodes.map((node) => ({
      ...node,
      position: positionById.get(node.id) ?? node.position,
    })),
    edges: nextLayout.edges,
  }
}

export async function layoutDagWithElk(
  nodes: DagStateNode[],
  edges: DagStateEdge[],
  goal?: string,
): Promise<DagFlowLayout> {
  if (nodes.length === 0) {
    return { nodes: [], edges: [] }
  }

  const rootGoal = rootGoalForLayout(goal, nodes)
  const originalNodeIds = new Set(nodes.map((node) => node.id))
  const incidentIds = realIncidentNodeIds(nodes, edges)
  const allEdges = [...goalEdgesFor(rootGoal, nodes, edges), ...edges]
  const elkEdges = allEdges.flatMap((edge): ElkExtendedEdge[] => {
    const edgeIsValid =
      (edge.from === DAG_GOAL_NODE_ID || originalNodeIds.has(edge.from))
      && originalNodeIds.has(edge.to)
    if (!edgeIsValid) return []
    return [{
      id: `${edge.from}-${edge.to}`,
      sources: [edge.from],
      targets: [edge.to],
    }]
  })

  const graph: ElkNode = {
    id: 'dag-root',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': 'DOWN',
      'elk.layered.spacing.nodeNodeBetweenLayers': '58',
      'elk.spacing.nodeNode': '34',
      'elk.edgeRouting': 'ORTHOGONAL',
      'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
      'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
      'elk.separateConnectedComponents': 'true',
      'elk.spacing.componentComponent': '54',
    },
    children: [
      ...(rootGoal
        ? [{ id: DAG_GOAL_NODE_ID, width: GOAL_NODE_WIDTH, height: GOAL_NODE_HEIGHT }]
        : []),
      ...nodes.map((node) => ({
        id: node.id,
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
      })),
    ],
    edges: elkEdges,
  }

  const layout = await elk.layout(graph)
  const childrenById = new Map((layout.children ?? []).map((node) => [node.id, node]))
  const goalChild = childrenById.get(DAG_GOAL_NODE_ID)
  const flowNodes = nodes.map((node, index) => {
    const child = childrenById.get(node.id)
    const fallback = seedPosition(index)
    return toFlowNode(node, {
      x: child?.x ?? fallback.x,
      y: child?.y ?? fallback.y,
      isStandalone: !incidentIds.has(node.id),
    })
  })
  const fullFlowNodes = rootGoal
    ? [goalFlowNode(rootGoal, goalChild?.x ?? 18, goalChild?.y ?? 18), ...flowNodes]
    : flowNodes
  const statusById = new Map<string, PlanDagNodeStatus>(
    nodes.map((node) => [node.id, node.status]),
  )
  const availableNodeIds = new Set(fullFlowNodes.map((node) => node.id))

  return {
    nodes: fullFlowNodes,
    edges: toFlowEdges(allEdges, availableNodeIds, statusById),
  }
}
