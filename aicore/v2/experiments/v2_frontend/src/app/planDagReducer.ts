import type {
  DiagnosisDecision,
  DiagnosisProcessErrorKind,
  DiagnosisSource,
  PlanConsoleEvent,
  PlanDefinition,
  PlanStepDefinition,
} from '../domain/planEvents'
import { asRecord, asString } from '../utils/unknown'

type PlanDagPageStatus =
  | 'planning'
  | 'running'
  | 'replanning'
  | 'replanned'
  | 'success'
  | 'partial'
  | 'failed'

export type PlanDagNodeStatus =
  | 'pending'
  | 'running'
  | 'diagnosing'
  | 'needs_replan'
  | 'success'
  | 'degraded'
  | 'unsolvable'
  | 'skipped'
  | 'failed'

interface PlanDiagnosisTraceBase {
  successCheck: string
  failureMessage: string
  processErrorKind?: DiagnosisProcessErrorKind
  startedAt: string
}

export type PlanDiagnosisTrace =
  | PlanDiagnosisTraceBase & { status: 'running' }
  | PlanDiagnosisTraceBase & {
      status: 'completed'
      source: DiagnosisSource
      decision: DiagnosisDecision
      completedAt: string
    }

export interface PlanDagNode extends PlanStepDefinition {
  id: string
  status: PlanDagNodeStatus
  diagnosis?: PlanDiagnosisTrace
  resolvedInputs?: Record<string, unknown>
  toolOutput?: unknown
  conceptOutput?: Record<string, unknown>
  processError?: unknown
  unmet?: unknown
  skipReason?: string
  runnerErrors: unknown[]
  startedAt?: string
  completedAt?: string
}

export interface PlanDagEdge {
  from: string
  to: string
}

export interface PlanDagPage {
  id: string
  messageId: string
  round: number
  title: string
  goal?: string
  status: PlanDagPageStatus
  plan?: PlanDefinition
  nodes: PlanDagNode[]
  edges: PlanDagEdge[]
  repairContext?: unknown
  runnerErrors: unknown[]
  roundErrors: unknown[]
  repairPolicy?: string
  finish?: { forced: boolean; reason?: string }
  createdAt: string
  updatedAt: string
  completedAt?: string
}

export interface PlannerState {
  pages: PlanDagPage[]
  activePageId?: string
  activeRoundByMessageId: Record<string, number>
}

export function initialPlannerState(): PlannerState {
  return { pages: [], activeRoundByMessageId: {} }
}

function planPageId(messageId: string, round: number): string {
  return `${messageId}:${round}`
}

function nodeFromStep(step: PlanStepDefinition): PlanDagNode {
  return {
    ...step,
    id: step.stepId,
    status: 'pending',
    runnerErrors: [],
  }
}

function edgesFromPlan(plan: PlanDefinition): PlanDagEdge[] {
  return plan.steps.flatMap((step) =>
    step.dependsOn.map((dependency) => ({ from: dependency, to: step.stepId })),
  )
}

function updatePage(
  state: PlannerState,
  pageId: string,
  updater: (page: PlanDagPage) => PlanDagPage,
): PlannerState {
  const currentPage = state.pages.find((page) => page.id === pageId)
  if (!currentPage || currentPage.status === 'replanned') return state
  return {
    ...state,
    pages: state.pages.map((page) => (page.id === pageId ? updater(page) : page)),
  }
}

function updateNode(
  page: PlanDagPage,
  stepId: string,
  updater: (node: PlanDagNode) => PlanDagNode,
): PlanDagPage {
  if (!page.nodes.some((node) => node.id === stepId)) return page
  return {
    ...page,
    nodes: page.nodes.map((node) => (node.id === stepId ? updater(node) : node)),
  }
}

function errorStepId(error: unknown): string | undefined {
  const record = asRecord(error)
  const detail = asRecord(record.detail)
  return asString(detail.step_id ?? record.step_id) || undefined
}

function unmetVerdict(value: unknown): string | undefined {
  return asString(asRecord(value).verdict) || undefined
}

function terminalEvidence(page: PlanDagPage): boolean {
  return page.nodes.some((node) =>
    node.toolOutput !== undefined || node.skipReason !== undefined,
  )
}

export function diagnosisStatus(decision: DiagnosisDecision): PlanDagNodeStatus {
  if (decision.outcome === 'replan') return 'needs_replan'
  if (decision.outcome === 'skip_unsolvable') return 'unsolvable'
  return 'degraded'
}

export function diagnosingNodeCount(page: PlanDagPage): number {
  return page.nodes.filter((node) => node.status === 'diagnosing').length
}

export function completedDiagnosisSummaries(page: PlanDagPage) {
  return page.nodes.flatMap((node) => {
    if (node.diagnosis?.status !== 'completed') return []
    return [{
      stepId: node.stepId,
      stepGoal: node.stepGoal,
      source: node.diagnosis.source,
      outcome: node.diagnosis.decision.outcome,
      decision: node.diagnosis.decision,
      completedAt: node.diagnosis.completedAt,
    }]
  }).sort((left, right) => left.completedAt.localeCompare(right.completedAt))
}

export function applyPlanEvent(
  state: PlannerState,
  event: PlanConsoleEvent,
): PlannerState {
  const pageId = planPageId(event.messageId, event.round)

  if (event.type === 'plact.round.start') {
    const previousRound = state.activeRoundByMessageId[event.messageId]
    const previousPageId = previousRound === undefined
      ? undefined
      : planPageId(event.messageId, previousRound)
    let pages = state.pages.map((page) =>
      page.id === previousPageId && page.status === 'replanning'
        ? { ...page, status: 'replanned' as const, updatedAt: event.timestamp }
        : page,
    )
    const existing = pages.find((page) => page.id === pageId)
    if (!existing) {
      pages = [...pages, {
        id: pageId,
        messageId: event.messageId,
        round: event.round,
        title: `Round ${event.round + 1}`,
        status: 'planning',
        nodes: [],
        edges: [],
        repairContext: event.repairContext,
        runnerErrors: [],
        roundErrors: [],
        createdAt: event.timestamp,
        updatedAt: event.timestamp,
      }]
    }
    return {
      ...state,
      pages,
      activePageId: pageId,
      activeRoundByMessageId: {
        ...state.activeRoundByMessageId,
        [event.messageId]: event.round,
      },
    }
  }

  if (event.type === 'plan.created') {
    return updatePage(state, pageId, (page) => ({
      ...page,
      goal: event.plan.goal,
      status: 'running',
      plan: event.plan,
      nodes: event.plan.steps.map(nodeFromStep),
      edges: edgesFromPlan(event.plan),
      updatedAt: event.timestamp,
    }))
  }

  if (event.type === 'plan.step.started') {
    return updatePage(state, pageId, (page) => ({
      ...updateNode(page, event.stepId, (node) => ({
        ...node,
        status: 'running',
        resolvedInputs: event.resolvedInputs,
        startedAt: event.timestamp,
      })),
      updatedAt: event.timestamp,
    }))
  }

  if (event.type === 'plan.step.diagnosis.started') {
    return updatePage(state, pageId, (page) => ({
      ...updateNode(page, event.stepId, (node) => {
        if (node.diagnosis !== undefined
          || (node.status !== 'pending' && node.status !== 'running')) return node
        return {
          ...node,
          status: 'diagnosing',
          diagnosis: {
            status: 'running',
            successCheck: event.successCheck,
            failureMessage: event.failureMessage,
            processErrorKind: event.processErrorKind,
            startedAt: event.timestamp,
          },
        }
      }),
      updatedAt: event.timestamp,
    }))
  }

  if (event.type === 'plan.step.diagnosis.completed') {
    return updatePage(state, pageId, (page) => ({
      ...updateNode(page, event.stepId, (node) => {
        if (node.diagnosis?.status !== 'running') return node
        return {
          ...node,
          status: diagnosisStatus(event.decision),
          diagnosis: {
            ...node.diagnosis,
            status: 'completed',
            source: event.source,
            decision: event.decision,
            completedAt: event.timestamp,
          },
        }
      }),
      updatedAt: event.timestamp,
    }))
  }

  if (event.type === 'plan.step.done') {
    const verdict = unmetVerdict(event.unmet)
    const status: PlanDagNodeStatus = verdict === 'degraded'
      ? 'degraded'
      : verdict === 'unsolvable'
        ? 'unsolvable'
        : event.processError === undefined
          ? 'success'
          : 'failed'
    return updatePage(state, pageId, (page) => ({
      ...updateNode(page, event.stepId, (node) => {
        const terminalStatus = node.diagnosis?.status === 'completed'
          ? diagnosisStatus(node.diagnosis.decision)
          : status
        return {
          ...node,
          stepGoal: event.stepGoal || node.stepGoal,
          rawInputs: event.rawInputs,
          resolvedInputs: event.resolvedInputs,
          toolOutput: event.toolOutput,
          conceptOutput: event.conceptOutput,
          processError: event.processError,
          unmet: event.unmet,
          status: terminalStatus,
          completedAt: event.timestamp,
        }
      }),
      updatedAt: event.timestamp,
    }))
  }

  if (event.type === 'plan.step.skipped') {
    return updatePage(state, pageId, (page) => ({
      ...updateNode(page, event.stepId, (node) => ({
        ...node,
        status: 'skipped',
        condition: event.condition ?? node.condition,
        skipReason: event.reason,
        completedAt: event.timestamp,
      })),
      updatedAt: event.timestamp,
    }))
  }

  if (event.type === 'plan.runner.error') {
    return updatePage(state, pageId, (page) => {
      let next: PlanDagPage = {
        ...page,
        status: 'replanning',
        runnerErrors: [...page.runnerErrors, ...event.errors],
        updatedAt: event.timestamp,
      }
      event.errors.forEach((error) => {
        const stepId = errorStepId(error)
        if (!stepId) return
        next = updateNode(next, stepId, (node) => ({
          ...node,
          status: node.diagnosis?.status === 'completed'
            && node.diagnosis.decision.outcome === 'replan'
            ? 'needs_replan'
            : 'failed',
          runnerErrors: [...node.runnerErrors, error],
          completedAt: node.completedAt ?? event.timestamp,
        }))
      })
      return next
    })
  }

  if (event.type === 'plact.errors') {
    return updatePage(state, pageId, (page) => ({
      ...page,
      status: 'replanning',
      roundErrors: [...page.roundErrors, ...event.errors],
      repairPolicy: event.policy,
      updatedAt: event.timestamp,
    }))
  }

  if (event.type === 'plact.finish') {
    return updatePage(state, pageId, (page) => ({
      ...page,
      status: event.forced
        ? (terminalEvidence(page) ? 'partial' : 'failed')
        : 'success',
      finish: { forced: event.forced, reason: event.reason },
      updatedAt: event.timestamp,
      completedAt: event.timestamp,
    }))
  }

  return state
}
