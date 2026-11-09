import type { Edge, Node } from '@xyflow/react'
import type {
  PlanDagEdge,
  PlanDagNode,
  PlanDagNodeStatus,
} from '../app/planDagReducer'

export type DagStateNode = PlanDagNode
export type DagStateEdge = PlanDagEdge

export interface PlanDagNodeData extends PlanDagNode, Record<string, unknown> {
  isStandalone: boolean
  isGoalRoot?: false
  isDetailSelected?: boolean
  onToggleDetail?: (node: DagNodeData) => void
}

export interface GoalDagNodeData extends Record<string, unknown> {
  id: string
  goal: string
  status: 'goal'
  isStandalone: false
  isGoalRoot: true
  isDetailSelected?: boolean
  onToggleDetail?: (node: DagNodeData) => void
}

export type DagNodeData = PlanDagNodeData | GoalDagNodeData

export interface DagEdgeData extends Record<string, unknown> {
  status: PlanDagNodeStatus | 'goal'
  relation: 'dependency' | 'goal'
}

export type DagFlowNode = Node<DagNodeData, 'dagNode'>
export type DagFlowEdge = Edge<DagEdgeData, 'dagEdge'>

export interface DagFlowLayout {
  nodes: DagFlowNode[]
  edges: DagFlowEdge[]
}
