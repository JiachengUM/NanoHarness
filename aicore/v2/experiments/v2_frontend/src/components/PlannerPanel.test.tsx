import { readFileSync } from 'node:fs'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { initialConsoleState, type ConsoleState } from '../app/consoleReducer'
import type { PlanDagNode } from '../app/planDagReducer'
import { getFocusWrapIndex } from '../utils/focus'
import {
  DAG_GOAL_NODE_ID,
  createDagSeedLayout,
  createDagStructureKey,
  createDagViewportKey,
  layoutDagWithElk,
  refreshDagLayoutData,
} from './dagLayout'
import { DagNodeCard, DagNodeDetailPanel } from './DagGraph'
import {
  PLANNER_FOCUSABLE_SELECTOR,
  PlannerPanel,
  resolvePlannerPageSelection,
} from './PlannerPanel'

const timestamp = '2026-07-10T10:00:00.000Z'

function node(overrides: Partial<PlanDagNode> = {}): PlanDagNode {
  return {
    id: 'lookup-cafe',
    stepId: 'lookup-cafe',
    stepGoal: '搜索附近评分较高的咖啡店',
    op: '地点搜索工具',
    dependsOn: [],
    rawInputs: { query: '${user.query}' },
    resolvedInputs: { query: '附近评分较高的咖啡店' },
    outputSpec: {
      is_list: true,
      concept: { name: 'Place', attributes: [{ name: 'address' }] },
    },
    condition: 'true',
    successCheck: '(.lookup.outputs.Place | length) > 0',
    status: 'running',
    runnerErrors: [],
    startedAt: timestamp,
    ...overrides,
  }
}

function diagnosingNode(): PlanDagNode {
  return node({
    status: 'diagnosing',
    diagnosis: {
      status: 'running',
      successCheck: '营业时间覆盖用户到店时段',
      failureMessage: '候选地点缺少夜间营业证据',
      processErrorKind: 'projection',
      startedAt: timestamp,
    },
  })
}

function completedDiagnosisNode(): PlanDagNode {
  return node({
    status: 'needs_replan',
    diagnosis: {
      status: 'completed',
      successCheck: '营业时间覆盖用户到店时段',
      failureMessage: '候选地点缺少夜间营业证据',
      processErrorKind: 'projection',
      source: 'llm',
      decision: {
        outcome: 'replan',
        failedAssumption: '候选地点会提供可靠的夜间营业信息',
        retryDirection: '改用支持营业时间筛选的数据源后重试',
      },
      startedAt: timestamp,
      completedAt: '2026-07-10T10:00:00.250Z',
    },
  })
}

function createPlannerState(): ConsoleState {
  return {
    ...initialConsoleState(),
    planner: {
      activePageId: 'agent-1:0',
      activeRoundByMessageId: { 'agent-1': 0 },
      pages: [{
        id: 'agent-1:0',
        messageId: 'agent-1',
        round: 0,
        title: 'Round 1',
        goal: '找到咖啡店后导航过去',
        status: 'running',
        nodes: [
          node(),
          node({
            id: 'navigate-there',
            stepId: 'navigate-there',
            stepGoal: '导航到选中的咖啡店',
            op: 'navigation',
            dependsOn: ['lookup-cafe'],
            rawInputs: { destination: '${lookup.outputs.Place[0].address}' },
            resolvedInputs: undefined,
            outputSpec: { is_list: false, concept: { name: 'Route' } },
            condition: undefined,
            successCheck: 'true',
            status: 'pending',
            startedAt: undefined,
          }),
          node({
            id: 'play-music',
            stepId: 'play-music',
            stepGoal: '播放音乐',
            op: 'media',
            dependsOn: [],
            rawInputs: {},
            resolvedInputs: {},
            outputSpec: { is_list: false, concept: { name: 'Playback' } },
            condition: undefined,
            successCheck: 'true',
            status: 'success',
            startedAt: timestamp,
            completedAt: '2026-07-10T10:00:01.000Z',
          }),
        ],
        edges: [{ from: 'lookup-cafe', to: 'navigate-there' }],
        runnerErrors: [],
        roundErrors: [],
        createdAt: timestamp,
        updatedAt: timestamp,
      }],
    },
  }
}

function createPagedPlannerState(): ConsoleState {
  const state = createPlannerState()
  const page = state.planner.pages[0]
  return {
    ...state,
    planner: {
      activePageId: 'agent-1:1',
      activeRoundByMessageId: { 'agent-1': 1 },
      pages: [
        { ...page, id: 'agent-1:0', round: 0, title: 'Round 1', status: 'replanned' },
        {
          ...page,
          id: 'agent-1:1',
          round: 1,
          title: 'Round 2',
          status: 'partial',
          repairPolicy: 'regenerate_plan',
          runnerErrors: [{ source: 'step.remediation', detail: { message: '扩大搜索范围后重试' } }],
          roundErrors: [{ source: 'step.remediation' }],
        },
      ],
    },
  }
}

function createFailedPlannerState(): ConsoleState {
  return {
    ...initialConsoleState(),
    planner: {
      activePageId: 'agent-failed:0',
      activeRoundByMessageId: { 'agent-failed': 0 },
      pages: [{
        id: 'agent-failed:0',
        messageId: 'agent-failed',
        round: 0,
        title: 'Round 1',
        status: 'failed',
        nodes: [],
        edges: [],
        runnerErrors: [{ source: 'plan.logic', detail: { message: 'weather 查询工具不在白名单中' } }],
        roundErrors: [],
        finish: { forced: true, reason: '计划未执行' },
        createdAt: timestamp,
        updatedAt: timestamp,
        completedAt: timestamp,
      }],
    },
  }
}

describe('PlannerPanel', () => {
  it('renders the human-readable stage title with its technical label', () => {
    const markup = renderToStaticMarkup(<PlannerPanel state={initialConsoleState()} />)

    expect(markup).toContain('<h2>任务如何展开</h2>')
    expect(markup).toContain('plan dag')
  })

  it('wraps fullscreen focus only at dialog boundaries', () => {
    expect(getFocusWrapIndex({
      currentIndex: 0,
      focusableCount: 3,
      backwards: true,
    })).toBe(2)
    expect(getFocusWrapIndex({
      currentIndex: 2,
      focusableCount: 3,
      backwards: false,
    })).toBe(0)
    expect(getFocusWrapIndex({
      currentIndex: 1,
      focusableCount: 3,
      backwards: false,
    })).toBeUndefined()
    expect(getFocusWrapIndex({
      currentIndex: -1,
      focusableCount: 3,
      backwards: false,
    })).toBe(0)
    expect(getFocusWrapIndex({
      currentIndex: -1,
      focusableCount: 3,
      backwards: true,
    })).toBe(2)
    expect(getFocusWrapIndex({
      currentIndex: 0,
      focusableCount: 0,
      backwards: false,
    })).toBeUndefined()
  })

  it('includes React Flow wrappers and standard controls in the focus trap', () => {
    ;[
      'a[href]',
      'button:not([disabled])',
      'input:not([disabled])',
      'select:not([disabled])',
      'textarea:not([disabled])',
      '[tabindex]:not([tabindex="-1"])',
      '[contenteditable="true"]',
    ].forEach((clause) => expect(PLANNER_FOCUSABLE_SELECTOR).toContain(clause))
  })

  it('preserves a historical selection when active page identity is unchanged', () => {
    expect(resolvePlannerPageSelection(
      'agent-1:0',
      'agent-1:1',
      'agent-1:1',
      ['agent-1:0', 'agent-1:1'],
    )).toBe('agent-1:0')
  })

  it('follows a newly created active page', () => {
    expect(resolvePlannerPageSelection(
      'agent-1:0',
      'agent-1:1',
      'agent-1:2',
      ['agent-1:0', 'agent-1:1', 'agent-1:2'],
    )).toBe('agent-1:2')
  })

  it('falls back to the latest page when the selected page is missing', () => {
    expect(resolvePlannerPageSelection(
      'agent-1:0',
      'agent-1:1',
      'agent-1:1',
      ['agent-1:1', 'agent-1:2'],
    )).toBe('agent-1:2')
  })

  it('renders an accessible fullscreen control for the Plan DAG view', () => {
    const markup = renderToStaticMarkup(<PlannerPanel state={createPlannerState()} />)

    expect(markup).toContain('aria-label="全屏查看任务拆解 DAG"')
    expect(markup).toContain('class="dag-fullscreen-toggle"')
  })

  it('renders request-aware repair navigation, status, and full round evidence', () => {
    const markup = renderToStaticMarkup(<PlannerPanel state={createPagedPlannerState()} />)

    expect(markup).toContain('请求 1 · Round 2 / 2')
    expect(markup).toContain('部分完成')
    expect(markup).toContain('aria-label="上一轮计划"')
    expect(markup).toContain('重规划证据')
    expect(markup).toContain('regenerate_plan')
    expect(markup).toContain('扩大搜索范围后重试')
  })

  it('does not render the same runner error twice as round evidence', () => {
    const state = createPagedPlannerState()
    const duplicated = { source: 'step.remediation', detail: { message: 'same evidence once' } }
    state.planner.pages[1] = {
      ...state.planner.pages[1],
      runnerErrors: [duplicated],
      roundErrors: [{ ...duplicated, detail: { ...duplicated.detail } }],
    }

    const markup = renderToStaticMarkup(<PlannerPanel state={state} />)

    expect(markup.match(/same evidence once/g)).toHaveLength(1)
  })

  it('renders a failed page with no nodes as an error instead of a fake graph', () => {
    const markup = renderToStaticMarkup(<PlannerPanel state={createFailedPlannerState()} />)

    expect(markup).toContain('class="dag-error-card"')
    expect(markup).toContain('Plan 执行失败')
    expect(markup).toContain('weather 查询工具不在白名单中')
    expect(markup).not.toContain('等待 DAG 计划')
  })

  it('uses ELK to place dependencies below parents and separate standalone nodes', async () => {
    const page = createPlannerState().planner.pages[0]
    const layout = await layoutDagWithElk(page.nodes, page.edges)
    const byId = Object.fromEntries(layout.nodes.map((item) => [item.id, item]))

    expect(byId['navigate-there'].position.y).toBeGreaterThan(byId['lookup-cafe'].position.y)
    expect(byId['play-music'].data.isStandalone).toBe(true)
    expect(layout.edges[0]).toMatchObject({
      id: 'lookup-cafe-navigate-there',
      source: 'lookup-cafe',
      target: 'navigate-there',
      animated: true,
    })
  })

  it('adds a neutral goal root linked to each entry node', () => {
    const page = createPlannerState().planner.pages[0]
    const layout = createDagSeedLayout(page.nodes, page.edges, page.goal)
    const goalNode = layout.nodes.find((item) => item.id === DAG_GOAL_NODE_ID)

    expect(goalNode?.data).toMatchObject({
      isGoalRoot: true,
      status: 'goal',
      goal: '找到咖啡店后导航过去',
    })
    expect(layout.edges).toEqual(expect.arrayContaining([
      expect.objectContaining({ source: DAG_GOAL_NODE_ID, target: 'lookup-cafe', animated: false }),
      expect.objectContaining({ source: DAG_GOAL_NODE_ID, target: 'play-music', animated: false }),
    ]))
  })

  it('keeps React Flow node wrappers pointer-interactive for detail controls', () => {
    const page = createPlannerState().planner.pages[0]
    const layout = createDagSeedLayout(page.nodes, page.edges, page.goal)

    expect(layout.nodes).toHaveLength(4)
    expect(layout.nodes.every((item) => item.style?.pointerEvents === 'all')).toBe(true)
  })

  it('renders non-numeric step ids and no fabricated progress UI', () => {
    const planNode = createPlannerState().planner.pages[0].nodes[0]
    const markup = renderToStaticMarkup(
      <DagNodeCard node={{ ...planNode, isStandalone: false }} />,
    )

    expect(markup).toContain('lookup-cafe')
    expect(markup).toContain('搜索附近评分较高的咖啡店')
    expect(markup).toContain('地点搜索工具')
    expect(markup).toContain('执行中')
    expect(markup).toContain('条件步骤')
    expect(markup).toContain('列表输出')
    expect(markup).not.toContain('dag-node-progress')
    expect(markup).not.toContain('当前进度')
    expect(markup).not.toMatch(/\d+%/)
  })

  it('renders a diagnosing card once without fabricated percentage progress', () => {
    const markup = renderToStaticMarkup(
      <DagNodeCard node={{ ...diagnosingNode(), isStandalone: false }} />,
    )

    expect(markup).toContain('诊断中')
    expect(markup).not.toContain('dag-diagnosis-tag')
    expect(markup).not.toMatch(/\d+%/)
  })

  it('renders complete Plan and runtime evidence in the detail panel', () => {
    const planNode = {
      ...createPlannerState().planner.pages[0].nodes[0],
      status: 'degraded' as const,
      toolOutput: { data: [{ name: 'A', address: '完整地址' }], error: null },
      conceptOutput: { Place: [{ name: 'A', address: '完整地址' }] },
      processError: { kind: 'projection', message: '字段映射不完整' },
      unmet: {
        verdict: 'degraded',
        message: '只找到一个候选',
        reason: '数据源覆盖有限',
        success_check: '(.lookup.outputs.Place | length) > 2',
      },
      runnerErrors: [{ source: 'step.remediation', detail: { message: '保留完整修复证据' } }],
      completedAt: '2026-07-10T10:00:03.000Z',
      isStandalone: false,
    }
    const markup = renderToStaticMarkup(
      <DagNodeDetailPanel node={planNode} onClose={() => undefined} />,
    )

    ;[
      'Step ID',
      '步骤目标',
      '调用工具',
      '依赖步骤',
      '执行条件',
      '成功检查',
      '输出定义',
      'Plan 原始输入',
      '实际工具输入',
      '工具原始结果',
      'Concept 输出',
      '过程错误',
      '未达成诊断',
      'Runner 错误',
      '开始时间',
      '完成时间',
      '完整地址',
      '保留完整修复证据',
    ].forEach((text) => expect(markup).toContain(text))
    expect(markup).not.toContain('当前进度')
  })

  it('renders the complete remediation diagnosis trace in node detail', () => {
    const markup = renderToStaticMarkup(
      <DagNodeDetailPanel
        node={{ ...completedDiagnosisNode(), isStandalone: false }}
        onClose={() => undefined}
      />,
    )

    ;[
      '补救诊断',
      'LLM',
      '需要重规划',
      '候选地点会提供可靠的夜间营业信息',
      '改用支持营业时间筛选的数据源后重试',
    ].forEach((text) => expect(markup).toContain(text))
  })

  it('renders a final-decision summary for a diagnosis-only round', () => {
    const state = createPlannerState()
    state.planner.pages[0] = {
      ...state.planner.pages[0],
      nodes: [completedDiagnosisNode()],
      edges: [],
      runnerErrors: [],
      roundErrors: [],
    }

    const markup = renderToStaticMarkup(<PlannerPanel state={state} />)

    ;[
      '最终裁决',
      'lookup-cafe',
      'LLM',
      '需要重规划',
      '改用支持营业时间筛选的数据源后重试',
    ].forEach((text) => expect(markup).toContain(text))
  })

  it('renders the diagnosing node count beside the selected page status', () => {
    const state = createPlannerState()
    state.planner.pages[0] = {
      ...state.planner.pages[0],
      nodes: [diagnosingNode()],
      edges: [],
    }

    const markup = renderToStaticMarkup(<PlannerPanel state={state} />)

    expect(markup).toContain('1 个节点诊断中')
  })

  it('disables diagnosis animation when the selected page is older than the latest page', () => {
    const state = createPagedPlannerState()
    state.planner.activePageId = 'agent-1:0'
    state.planner.activeRoundByMessageId['agent-1'] = 0
    state.planner.pages[0] = {
      ...state.planner.pages[0],
      status: 'running',
      nodes: [diagnosingNode()],
      edges: [],
    }

    const markup = renderToStaticMarkup(<PlannerPanel state={state} />)

    expect(markup).toContain('class="dag-flow-container diagnosis-animation-disabled"')
  })

  it('changes the viewport key when ELK replaces the seed layout', async () => {
    const page = createPlannerState().planner.pages[0]
    const seedLayout = createDagSeedLayout(page.nodes, page.edges)
    const elkLayout = await layoutDagWithElk(page.nodes, page.edges)

    expect(createDagViewportKey(elkLayout)).not.toBe(createDagViewportKey(seedLayout))
  })

  it('keeps the viewport key stable when the same graph data is reordered', () => {
    const page = createPlannerState().planner.pages[0]
    const layout = createDagSeedLayout(page.nodes, page.edges, page.goal)
    const reorderedLayout = {
      nodes: [...layout.nodes].reverse(),
      edges: [...layout.edges].reverse(),
    }

    expect(createDagViewportKey(reorderedLayout)).toBe(createDagViewportKey(layout))
  })

  it('refreshes live node and edge data without changing the viewport key', () => {
    const initialNodes = [
      node({ id: 'source', stepId: 'source', status: 'running' }),
      node({ id: 'target', stepId: 'target', status: 'running' }),
    ]
    const edges = [{ from: 'source', to: 'target' }]
    const initialLayout = createDagSeedLayout(initialNodes, edges, '完成任务')
    const initialViewportKey = createDagViewportKey(initialLayout)
    const refreshed = refreshDagLayoutData(
      initialLayout,
      [
        node({ id: 'source', stepId: 'source', status: 'running' }),
        {
          ...diagnosingNode(),
          id: 'target',
          stepId: 'target',
        },
      ],
      edges,
      '更新后的任务',
    )

    expect(refreshed.nodes.find((item) => item.id === 'target')?.data.status).toBe('diagnosing')
    expect(refreshed.nodes.find((item) => item.id === DAG_GOAL_NODE_ID)?.data.goal).toBe(
      '更新后的任务',
    )
    expect(refreshed.edges[1]).toMatchObject({
      source: 'source',
      target: 'target',
      animated: false,
      data: { status: 'pending' },
    })
    expect(createDagViewportKey(refreshed)).toBe(initialViewportKey)
  })

  it('keys DAG structure by goal-root presence rather than goal label text', () => {
    const edges = [{ from: 'lookup-cafe', to: 'navigate-there' }]
    const pendingNodes = [
      node({ status: 'pending', diagnosis: undefined, startedAt: undefined }),
      node({ id: 'navigate-there', stepId: 'navigate-there', status: 'pending' }),
    ]
    const liveNodes = [
      diagnosingNode(),
      node({ id: 'navigate-there', stepId: 'navigate-there', status: 'running' }),
    ]

    expect(createDagStructureKey(liveNodes, edges, '完成任务')).toBe(
      createDagStructureKey(pendingNodes, edges, '完成任务'),
    )
    expect(createDagStructureKey(liveNodes, edges, '新任务')).toBe(
      createDagStructureKey(pendingNodes, edges, '完成任务'),
    )
    expect(createDagStructureKey(liveNodes, edges)).not.toBe(
      createDagStructureKey(pendingNodes, edges, '完成任务'),
    )
    expect(createDagStructureKey([], [], '完成任务')).toBe(
      createDagStructureKey([], []),
    )
  })

  it('keeps edges incident to diagnosis states pending and not animated', () => {
    const edges = [{ from: 'source', to: 'target' }]
    const diagnosingLayout = createDagSeedLayout([
      node({ id: 'source', stepId: 'source', status: 'running' }),
      { ...diagnosingNode(), id: 'target', stepId: 'target' },
    ], edges)
    const replanLayout = createDagSeedLayout([
      node({ id: 'source', stepId: 'source', status: 'needs_replan' }),
      node({ id: 'target', stepId: 'target', status: 'running' }),
    ], edges)

    ;[diagnosingLayout.edges[0], replanLayout.edges[0]].forEach((edge) => {
      expect(edge).toMatchObject({
        animated: false,
        data: { status: 'pending' },
      })
    })
  })

  it('renders React Flow and removes the old handwritten SVG canvas', () => {
    const markup = renderToStaticMarkup(<PlannerPanel state={createPlannerState()} />)

    expect(markup).toContain('react-flow')
    expect(markup).not.toContain('class="dag-stage"')
    expect(markup).not.toContain('class="dag-edge-flow')
  })

  it('disables diagnosis pulse for history and contains no DAG progress styles', () => {
    const css = readFileSync(new URL('../styles.css', import.meta.url), 'utf8')

    expect(css).toContain('.diagnosis-animation-disabled .node-diagnosing .dag-status-pulse')
    expect(css).not.toContain('.dag-node-progress')
    expect(css).not.toContain('dag-progress-shimmer')
    expect(css).not.toContain('dag-pending-blink')
  })
})
