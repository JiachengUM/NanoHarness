export type AgentMode = 'react' | 'plact'

export type DiagnosisSource = 'rule' | 'llm' | 'fallback'

export type DiagnosisProcessErrorKind =
  | 'params'
  | 'condition'
  | 'execution'
  | 'projection'

export type DiagnosisDecision =
  | {
      outcome: 'replan'
      failedAssumption: string
      retryDirection: string
    }
  | {
      outcome: 'skip_unsolvable'
      unsolvableReason: string
    }
  | {
      outcome: 'accept_degraded'
      limitation: string
    }

interface PlanEventContext {
  id: string
  timestamp: string
  messageId: string
  round: number
}

export interface PlanStepDefinition {
  stepId: string
  stepGoal: string
  op: string
  dependsOn: string[]
  rawInputs: Record<string, unknown>
  outputSpec: unknown
  condition?: string
  successCheck: string
}

export interface PlanDefinition {
  goal: string
  steps: PlanStepDefinition[]
  raw: unknown
}

interface PlActRoundStartEvent extends PlanEventContext {
  type: 'plact.round.start'
  repairContext?: unknown
}

interface PlanCreatedEvent extends PlanEventContext {
  type: 'plan.created'
  plan: PlanDefinition
}

interface PlanStepStartedEvent extends PlanEventContext {
  type: 'plan.step.started'
  stepId: string
  stepGoal: string
  resolvedInputs: Record<string, unknown>
}

export interface PlanStepDiagnosisStartedEvent extends PlanEventContext {
  type: 'plan.step.diagnosis.started'
  stepId: string
  stepGoal: string
  successCheck: string
  failureMessage: string
  processErrorKind?: DiagnosisProcessErrorKind
}

export interface PlanStepDiagnosisCompletedEvent extends PlanEventContext {
  type: 'plan.step.diagnosis.completed'
  stepId: string
  stepGoal: string
  source: DiagnosisSource
  decision: DiagnosisDecision
}

interface PlanStepDoneEvent extends PlanEventContext {
  type: 'plan.step.done'
  stepId: string
  stepGoal: string
  rawInputs: Record<string, unknown>
  resolvedInputs: Record<string, unknown>
  toolOutput: unknown
  conceptOutput: Record<string, unknown>
  processError?: unknown
  unmet?: unknown
}

export interface PlanStepSkippedEvent extends PlanEventContext {
  type: 'plan.step.skipped'
  stepId: string
  stepGoal: string
  reason: 'condition_false' | 'upstream_skipped' | 'upstream_unsolvable'
  condition?: string
}

interface PlanRunnerErrorEvent extends PlanEventContext {
  type: 'plan.runner.error'
  errors: unknown[]
}

interface PlActErrorsEvent extends PlanEventContext {
  type: 'plact.errors'
  errors: unknown[]
  policy: string
}

interface PlActFinishEvent extends PlanEventContext {
  type: 'plact.finish'
  response: unknown
  forced: boolean
  reason?: string
}

export type PlanConsoleEvent =
  | PlActRoundStartEvent
  | PlanCreatedEvent
  | PlanStepStartedEvent
  | PlanStepDiagnosisStartedEvent
  | PlanStepDiagnosisCompletedEvent
  | PlanStepDoneEvent
  | PlanStepSkippedEvent
  | PlanRunnerErrorEvent
  | PlActErrorsEvent
  | PlActFinishEvent

export function isPlanConsoleEvent(event: { type: string }): event is PlanConsoleEvent {
  return event.type.startsWith('plan.') || event.type.startsWith('plact.')
}
