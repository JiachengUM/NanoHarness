import { describe, expect, it } from 'vitest'
import type { PlanConsoleEvent, PlanDefinition } from '../domain/planEvents'
import {
  applyPlanEvent,
  completedDiagnosisSummaries,
  diagnosingNodeCount,
  initialPlannerState,
} from './planDagReducer'

const timestamp = '2026-07-10T10:00:00.000Z'

function plan(goal: string, suffix: string): PlanDefinition {
  return {
    goal,
    raw: { goal },
    steps: [
      {
        stepId: `search-${suffix}`,
        stepGoal: 'find a place',
        op: '地点搜索工具',
        dependsOn: [],
        rawInputs: { query: '${user.query}' },
        outputSpec: {
          is_list: true,
          concept: { name: 'Place', attributes: [{ name: 'address' }] },
        },
        successCheck: 'true',
      },
      {
        stepId: `navigate-${suffix}`,
        stepGoal: 'navigate there',
        op: 'navigation',
        dependsOn: [`search-${suffix}`],
        rawInputs: { destination: '${search.outputs.Place[0].address}' },
        outputSpec: { is_list: false, concept: { name: 'Route' } },
        condition: 'true',
        successCheck: 'true',
      },
    ],
  }
}

type PlanEventInput = PlanConsoleEvent extends infer EventT
  ? EventT extends PlanConsoleEvent
    ? Omit<EventT, 'id' | 'timestamp' | 'messageId'>
    : never
  : never

let eventSequence = 0

function event(value: PlanEventInput, eventTimestamp = timestamp): PlanConsoleEvent {
  eventSequence += 1
  return {
    id: `event-${eventSequence}`,
    timestamp: eventTimestamp,
    messageId: 'agent-1',
    ...value,
  } as PlanConsoleEvent
}

describe('planDagReducer', () => {
  it('tracks diagnosis lifecycle and preserves replan status through step completion', () => {
    let state = initialPlannerState()
    state = applyPlanEvent(state, event({ type: 'plact.round.start', round: 0 }))
    state = applyPlanEvent(state, event({
      type: 'plan.created',
      round: 0,
      plan: plan('diagnose failed search', 'r0'),
    }))
    state = applyPlanEvent(state, event({
      type: 'plan.step.started',
      round: 0,
      stepId: 'search-r0',
      stepGoal: 'find a place',
      resolvedInputs: { query: 'coffee' },
    }))
    state = applyPlanEvent(state, event({
      type: 'plan.step.diagnosis.started',
      round: 0,
      stepId: 'search-r0',
      stepGoal: 'find a place',
      successCheck: '.Place | length > 0',
      failureMessage: 'no matching place',
      processErrorKind: 'execution',
    }))

    expect(state.pages[0].status).toBe('running')
    expect(state.pages[0].nodes[0]).toMatchObject({
      status: 'diagnosing',
      diagnosis: {
        status: 'running',
        successCheck: '.Place | length > 0',
        failureMessage: 'no matching place',
        processErrorKind: 'execution',
        startedAt: timestamp,
      },
    })

    const decision = {
      outcome: 'replan' as const,
      failedAssumption: 'the provider covers this area',
      retryDirection: 'use a broader provider',
    }
    state = applyPlanEvent(state, event({
      type: 'plan.step.diagnosis.completed',
      round: 0,
      stepId: 'search-r0',
      stepGoal: 'find a place',
      source: 'llm',
      decision,
    }))
    state = applyPlanEvent(state, event({
      type: 'plan.step.done',
      round: 0,
      stepId: 'search-r0',
      stepGoal: 'find a place',
      rawInputs: { query: '${user.query}' },
      resolvedInputs: { query: 'coffee' },
      toolOutput: { data: [] },
      conceptOutput: {},
      processError: { message: 'provider unavailable' },
    }))

    expect(state.pages[0].nodes[0]).toMatchObject({
      status: 'needs_replan',
      rawInputs: { query: '${user.query}' },
      resolvedInputs: { query: 'coffee' },
      toolOutput: { data: [] },
      conceptOutput: {},
      processError: { message: 'provider unavailable' },
      completedAt: timestamp,
      diagnosis: {
        status: 'completed',
        successCheck: '.Place | length > 0',
        failureMessage: 'no matching place',
        processErrorKind: 'execution',
        startedAt: timestamp,
        source: 'llm',
        decision,
        completedAt: timestamp,
      },
    })
  })

  it('derives active diagnosis count and completed diagnosis summaries from nodes', () => {
    let state = initialPlannerState()
    const basePlan = plan('accept a degraded search', 'r0')
    const diagnosisPlan: PlanDefinition = {
      ...basePlan,
      steps: [
        ...basePlan.steps,
        {
          ...basePlan.steps[1],
          stepId: 'summarize-r0',
          stepGoal: 'summarize limitations',
          dependsOn: ['navigate-r0'],
        },
      ],
    }
    state = applyPlanEvent(state, event({ type: 'plact.round.start', round: 0 }))
    state = applyPlanEvent(state, event({
      type: 'plan.created',
      round: 0,
      plan: diagnosisPlan,
    }))
    state = applyPlanEvent(state, event({
      type: 'plan.step.diagnosis.started',
      round: 0,
      stepId: 'search-r0',
      stepGoal: 'find a place',
      successCheck: '.Place | length >= 3',
      failureMessage: 'only one candidate',
    }))

    expect(diagnosingNodeCount(state.pages[0])).toBe(1)
    expect(completedDiagnosisSummaries(state.pages[0])).toEqual([])

    state = applyPlanEvent(state, event({
      type: 'plan.step.diagnosis.started',
      round: 0,
      stepId: 'navigate-r0',
      stepGoal: 'navigate there',
      successCheck: '.Route != null',
      failureMessage: 'route unavailable',
    }))
    state = applyPlanEvent(state, event({
      type: 'plan.step.diagnosis.started',
      round: 0,
      stepId: 'summarize-r0',
      stepGoal: 'summarize limitations',
      successCheck: '.Summary != null',
      failureMessage: 'summary unavailable',
    }))

    const decision = {
      outcome: 'accept_degraded' as const,
      limitation: 'only one candidate is available',
    }
    state = applyPlanEvent(state, event({
      type: 'plan.step.diagnosis.completed',
      round: 0,
      stepId: 'search-r0',
      stepGoal: 'find a place',
      source: 'rule',
      decision,
    }, '2026-07-10T10:00:03.000Z'))
    const unsolvableDecision = {
      outcome: 'skip_unsolvable' as const,
      unsolvableReason: 'navigation provider is unavailable',
    }
    state = applyPlanEvent(state, event({
      type: 'plan.step.diagnosis.completed',
      round: 0,
      stepId: 'navigate-r0',
      stepGoal: 'navigate there',
      source: 'fallback',
      decision: unsolvableDecision,
    }, '2026-07-10T10:00:01.000Z'))
    const replanDecision = {
      outcome: 'replan' as const,
      failedAssumption: 'a route is required',
      retryDirection: 'return a place summary instead',
    }
    state = applyPlanEvent(state, event({
      type: 'plan.step.diagnosis.completed',
      round: 0,
      stepId: 'summarize-r0',
      stepGoal: 'summarize limitations',
      source: 'llm',
      decision: replanDecision,
    }, '2026-07-10T10:00:01.000Z'))

    expect(diagnosingNodeCount(state.pages[0])).toBe(0)
    expect(completedDiagnosisSummaries(state.pages[0])).toEqual([
      {
        stepId: 'navigate-r0',
        stepGoal: 'navigate there',
        source: 'fallback',
        outcome: 'skip_unsolvable',
        decision: unsolvableDecision,
        completedAt: '2026-07-10T10:00:01.000Z',
      },
      {
        stepId: 'summarize-r0',
        stepGoal: 'summarize limitations',
        source: 'llm',
        outcome: 'replan',
        decision: replanDecision,
        completedAt: '2026-07-10T10:00:01.000Z',
      },
      {
        stepId: 'search-r0',
        stepGoal: 'find a place',
        source: 'rule',
        outcome: 'accept_degraded',
        decision,
        completedAt: '2026-07-10T10:00:03.000Z',
      },
    ])
  })

  it('ignores diagnosis completion without a running trace or matching node', () => {
    let state = initialPlannerState()
    state = applyPlanEvent(state, event({ type: 'plact.round.start', round: 0 }))
    state = applyPlanEvent(state, event({
      type: 'plan.created',
      round: 0,
      plan: plan('keep pending nodes unchanged', 'r0'),
    }))
    const completion = {
      type: 'plan.step.diagnosis.completed' as const,
      round: 0,
      stepGoal: 'find a place',
      source: 'fallback' as const,
      decision: {
        outcome: 'skip_unsolvable' as const,
        unsolvableReason: 'required source is unavailable',
      },
    }

    state = applyPlanEvent(state, event({ ...completion, stepId: 'search-r0' }))

    expect(state.pages[0].nodes[0]).toMatchObject({
      id: 'search-r0',
      status: 'pending',
    })
    expect(state.pages[0].nodes[0].diagnosis).toBeUndefined()

    state = applyPlanEvent(state, event({ ...completion, stepId: 'missing' }))

    expect(state.pages[0].nodes).toHaveLength(2)
  })

  it('does not replace a running diagnosis trace with a duplicate start', () => {
    let state = initialPlannerState()
    state = applyPlanEvent(state, event({ type: 'plact.round.start', round: 0 }))
    state = applyPlanEvent(state, event({
      type: 'plan.created',
      round: 0,
      plan: plan('keep the first diagnosis start', 'r0'),
    }))
    state = applyPlanEvent(state, event({
      type: 'plan.step.diagnosis.started',
      round: 0,
      stepId: 'search-r0',
      stepGoal: 'find a place',
      successCheck: '.Place | length > 0',
      failureMessage: 'first failure',
      processErrorKind: 'execution',
    }, '2026-07-10T10:00:01.000Z'))
    state = applyPlanEvent(state, event({
      type: 'plan.step.diagnosis.started',
      round: 0,
      stepId: 'search-r0',
      stepGoal: 'find a place',
      successCheck: '.Place | length >= 3',
      failureMessage: 'duplicate failure',
      processErrorKind: 'projection',
    }, '2026-07-10T10:00:02.000Z'))

    expect(state.pages[0].nodes[0]).toMatchObject({
      status: 'diagnosing',
      diagnosis: {
        status: 'running',
        successCheck: '.Place | length > 0',
        failureMessage: 'first failure',
        processErrorKind: 'execution',
        startedAt: '2026-07-10T10:00:01.000Z',
      },
    })
  })

  it('does not reopen a completed node with a late diagnosis start', () => {
    let state = initialPlannerState()
    state = applyPlanEvent(state, event({ type: 'plact.round.start', round: 0 }))
    state = applyPlanEvent(state, event({
      type: 'plan.created',
      round: 0,
      plan: plan('keep completed diagnosis terminal', 'r0'),
    }))
    state = applyPlanEvent(state, event({
      type: 'plan.step.diagnosis.started',
      round: 0,
      stepId: 'search-r0',
      stepGoal: 'find a place',
      successCheck: '.Place | length > 0',
      failureMessage: 'no result',
    }, '2026-07-10T10:00:01.000Z'))
    const decision = {
      outcome: 'replan' as const,
      failedAssumption: 'the query is specific enough',
      retryDirection: 'rewrite the query',
    }
    state = applyPlanEvent(state, event({
      type: 'plan.step.diagnosis.completed',
      round: 0,
      stepId: 'search-r0',
      stepGoal: 'find a place',
      source: 'llm',
      decision,
    }, '2026-07-10T10:00:02.000Z'))
    state = applyPlanEvent(state, event({
      type: 'plan.step.done',
      round: 0,
      stepId: 'search-r0',
      stepGoal: 'find a place',
      rawInputs: { query: '${user.query}' },
      resolvedInputs: { query: 'coffee' },
      toolOutput: { data: [] },
      conceptOutput: {},
      processError: { message: 'no result' },
    }, '2026-07-10T10:00:03.000Z'))
    state = applyPlanEvent(state, event({
      type: 'plan.step.diagnosis.started',
      round: 0,
      stepId: 'search-r0',
      stepGoal: 'find a place',
      successCheck: '.Place | length >= 3',
      failureMessage: 'late duplicate',
    }, '2026-07-10T10:00:04.000Z'))

    expect(state.pages[0].nodes[0]).toMatchObject({
      status: 'needs_replan',
      completedAt: '2026-07-10T10:00:03.000Z',
      diagnosis: {
        status: 'completed',
        successCheck: '.Place | length > 0',
        failureMessage: 'no result',
        startedAt: '2026-07-10T10:00:01.000Z',
        source: 'llm',
        decision,
        completedAt: '2026-07-10T10:00:02.000Z',
      },
    })
  })

  it('keeps completed replan diagnosis terminal and preserves factual completion time', () => {
    let state = initialPlannerState()
    state = applyPlanEvent(state, event({ type: 'plact.round.start', round: 0 }))
    state = applyPlanEvent(state, event({
      type: 'plan.created',
      round: 0,
      plan: plan('repair failed search', 'r0'),
    }))
    state = applyPlanEvent(state, event({
      type: 'plan.step.diagnosis.started',
      round: 0,
      stepId: 'search-r0',
      stepGoal: 'find a place',
      successCheck: '.Place | length > 0',
      failureMessage: 'no result',
    }))
    state = applyPlanEvent(state, event({
      type: 'plan.step.diagnosis.completed',
      round: 0,
      stepId: 'search-r0',
      stepGoal: 'find a place',
      source: 'llm',
      decision: {
        outcome: 'replan',
        failedAssumption: 'the query is specific enough',
        retryDirection: 'rewrite the query',
      },
    }, '2026-07-10T10:00:01.000Z'))
    state = applyPlanEvent(state, event({
      type: 'plan.step.done',
      round: 0,
      stepId: 'search-r0',
      stepGoal: 'find a place',
      rawInputs: { query: '${user.query}' },
      resolvedInputs: { query: 'coffee' },
      toolOutput: { data: [] },
      conceptOutput: {},
      processError: { message: 'no result' },
    }, '2026-07-10T10:00:02.000Z'))

    expect(state.pages[0].nodes[0]).toMatchObject({
      status: 'needs_replan',
      completedAt: '2026-07-10T10:00:02.000Z',
      toolOutput: { data: [] },
      processError: { message: 'no result' },
    })

    const runnerError = {
      source: 'step.remediation',
      detail: { step_id: 'search-r0', message: 'rewrite the query' },
    }
    state = applyPlanEvent(state, event({
      type: 'plan.runner.error',
      round: 0,
      errors: [runnerError],
    }, '2026-07-10T10:00:03.000Z'))

    expect(state.pages[0].status).toBe('replanning')
    expect(state.pages[0].nodes[0]).toMatchObject({
      status: 'needs_replan',
      completedAt: '2026-07-10T10:00:02.000Z',
      runnerErrors: [runnerError],
      toolOutput: { data: [] },
      processError: { message: 'no result' },
    })
  })

  it('retains each repair round and all runtime evidence', () => {
    let state = initialPlannerState()
    const events: PlanConsoleEvent[] = [
      event({ type: 'plact.round.start', round: 0 }),
      event({ type: 'plan.created', round: 0, plan: plan('first plan', 'r0') }),
      event({
        type: 'plan.step.started',
        round: 0,
        stepId: 'search-r0',
        stepGoal: 'find a place',
        resolvedInputs: { query: 'coffee' },
      }),
      event({
        type: 'plan.runner.error',
        round: 0,
        errors: [{ source: 'step.remediation', detail: { step_id: 'search-r0', message: 'retry' } }],
      }),
      event({
        type: 'plact.errors',
        round: 0,
        errors: [{ source: 'step.remediation' }],
        policy: 'regenerate_plan',
      }),
      event({ type: 'plact.round.start', round: 1, repairContext: { failed_plan: 'first plan' } }),
      event({ type: 'plan.created', round: 1, plan: plan('second plan', 'r1') }),
      event({
        type: 'plan.step.started',
        round: 1,
        stepId: 'search-r1',
        stepGoal: 'find a place',
        resolvedInputs: { query: 'coffee near me' },
      }),
      event({
        type: 'plan.step.done',
        round: 1,
        stepId: 'search-r1',
        stepGoal: 'find a place',
        rawInputs: { query: '${user.query}' },
        resolvedInputs: { query: 'coffee near me' },
        toolOutput: { data: [{ name: 'A' }] },
        conceptOutput: { Place: [{ name: 'A', address: 'full address' }] },
        unmet: {
          verdict: 'degraded',
          message: 'only one candidate',
          reason: 'limited result',
          success_check: 'true',
        },
      }),
      event({
        type: 'plan.step.skipped',
        round: 1,
        stepId: 'navigate-r1',
        stepGoal: 'navigate there',
        reason: 'condition_false',
        condition: 'false',
      }),
      event({
        type: 'plact.finish',
        round: 1,
        response: 'partial answer',
        forced: true,
        reason: 'limited result',
      }),
    ]

    events.forEach((item) => { state = applyPlanEvent(state, item) })

    expect(state.pages).toHaveLength(2)
    expect(state.pages[0]).toMatchObject({
      id: 'agent-1:0',
      status: 'replanned',
      repairPolicy: 'regenerate_plan',
    })
    expect(state.pages[0].nodes[0]).toMatchObject({
      id: 'search-r0',
      status: 'failed',
      resolvedInputs: { query: 'coffee' },
    })
    expect(state.pages[1]).toMatchObject({
      id: 'agent-1:1',
      goal: 'second plan',
      status: 'partial',
    })
    expect(state.pages[1].edges).toEqual([{ from: 'search-r1', to: 'navigate-r1' }])
    expect(state.pages[1].nodes[0]).toMatchObject({
      status: 'degraded',
      rawInputs: { query: '${user.query}' },
      resolvedInputs: { query: 'coffee near me' },
      toolOutput: { data: [{ name: 'A' }] },
      conceptOutput: { Place: [{ name: 'A', address: 'full address' }] },
    })
    expect(state.pages[1].nodes[1]).toMatchObject({
      status: 'skipped',
      skipReason: 'condition_false',
    })
    expect(state.activePageId).toBe('agent-1:1')

    const frozenRound = state.pages[0]
    state = applyPlanEvent(state, event({
      type: 'plan.step.done',
      round: 0,
      stepId: 'search-r0',
      stepGoal: 'late result',
      rawInputs: {},
      resolvedInputs: {},
      toolOutput: { data: 'late' },
      conceptOutput: {},
    }))
    expect(state.pages[0]).toEqual(frozenRound)
  })

  it('maps forced finish to failed when no step has terminal evidence', () => {
    let state = initialPlannerState()
    state = applyPlanEvent(state, event({ type: 'plact.round.start', round: 0 }))
    state = applyPlanEvent(state, event({ type: 'plan.created', round: 0, plan: plan('never ran', 'r0') }))
    state = applyPlanEvent(state, event({
      type: 'plact.finish',
      round: 0,
      response: 'unable',
      forced: true,
      reason: 'schema failure',
    }))

    expect(state.pages[0].status).toBe('failed')
  })

  it('maps forced finish to partial after a factual done event even when the node failed', () => {
    let state = initialPlannerState()
    state = applyPlanEvent(state, event({ type: 'plact.round.start', round: 0 }))
    state = applyPlanEvent(state, event({ type: 'plan.created', round: 0, plan: plan('partially ran', 'r0') }))
    state = applyPlanEvent(state, event({
      type: 'plan.step.done',
      round: 0,
      stepId: 'search-r0',
      stepGoal: 'find a place',
      rawInputs: { query: '${user.query}' },
      resolvedInputs: { query: 'coffee' },
      toolOutput: { error: 'tool failed' },
      conceptOutput: {},
      processError: { message: 'tool failed' },
    }))
    state = applyPlanEvent(state, event({
      type: 'plact.finish',
      round: 0,
      response: 'partial answer',
      forced: true,
      reason: 'step failed after execution began',
    }))

    expect(state.pages[0].nodes[0].status).toBe('failed')
    expect(state.pages[0].status).toBe('partial')
  })

  it('does not create phantom pages or nodes for out-of-order terminal events', () => {
    let state = initialPlannerState()
    state = applyPlanEvent(state, event({
      type: 'plan.step.done',
      round: 0,
      stepId: 'missing',
      stepGoal: 'missing',
      rawInputs: {},
      resolvedInputs: {},
      toolOutput: {},
      conceptOutput: {},
    }))

    expect(state.pages).toEqual([])
  })

  it('keeps unsolvable and upstream-unsolvable distinct from ordinary failure', () => {
    let state = initialPlannerState()
    state = applyPlanEvent(state, event({ type: 'plact.round.start', round: 0 }))
    state = applyPlanEvent(state, event({ type: 'plan.created', round: 0, plan: plan('blocked', 'r0') }))
    state = applyPlanEvent(state, event({
      type: 'plan.step.done',
      round: 0,
      stepId: 'search-r0',
      stepGoal: 'find a place',
      rawInputs: { query: '${user.query}' },
      resolvedInputs: { query: 'impossible target' },
      toolOutput: { data: [] },
      conceptOutput: {},
      unmet: {
        verdict: 'unsolvable',
        success_check: 'true',
        message: 'no result',
        reason: 'source has no matching place',
      },
    }))
    state = applyPlanEvent(state, event({
      type: 'plan.step.skipped',
      round: 0,
      stepId: 'navigate-r0',
      stepGoal: 'navigate there',
      reason: 'upstream_unsolvable',
    }))

    expect(state.pages[0].nodes[0].status).toBe('unsolvable')
    expect(state.pages[0].nodes[1]).toMatchObject({
      status: 'skipped',
      skipReason: 'upstream_unsolvable',
    })
  })

  it('maps an unforced finish to page success', () => {
    let state = initialPlannerState()
    state = applyPlanEvent(state, event({ type: 'plact.round.start', round: 0 }))
    state = applyPlanEvent(state, event({
      type: 'plact.finish',
      round: 0,
      response: 'answer',
      forced: false,
    }))

    expect(state.pages[0].status).toBe('success')
  })
})
