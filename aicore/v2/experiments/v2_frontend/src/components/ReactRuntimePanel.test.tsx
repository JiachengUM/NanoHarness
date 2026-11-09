import { readFileSync } from 'node:fs'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import type {
  RuntimeTraceEntry,
  RuntimeTraceState,
} from '../app/runtimeTraceReducer'
import type {
  TaskProjection,
  TaskProjectionState,
} from '../domain/projection'
import { extractCssAtRuleBlock } from '../test/css'
import {
  ReactRuntimePanel,
  RuntimeTaskBlock,
  focusRuntimeAfterReturn,
  getRuntimeContentEndX,
  getRuntimeEntryStatusLabel,
  getRuntimeResizeScrollTarget,
  getRuntimeScrollTarget,
  getRuntimeTaskScrollTarget,
  isRuntimeAtLiveEdge,
  isRuntimeTaskAtLiveEdge,
  shouldRunRuntimeTimer,
} from './ReactRuntimePanel'

const START = '2026-07-13T08:00:00.000Z'
const START_MS = Date.parse(START)

function at(seconds: number): string {
  return new Date(START_MS + seconds * 1000).toISOString()
}

function runtimeTrace(entries: RuntimeTraceEntry[]): RuntimeTraceState {
  return { entries }
}

function task(overrides: Partial<TaskProjection> = {}): TaskProjection {
  return {
    taskId: 'task-1',
    toolName: 'search_places',
    title: '搜索附近评分较高的咖啡店',
    arguments: { query: '咖啡店' },
    status: 'success',
    progress: 100,
    trace: ['已返回候选地点'],
    createdAt: at(2),
    startedAt: at(2),
    updatedAt: at(5),
    completedAt: at(5),
    ...overrides,
  }
}

function taskState(items: TaskProjection[]): TaskProjectionState {
  return {
    byId: Object.fromEntries(items.map((item) => [item.taskId, item])),
    order: items.map((item) => item.taskId),
  }
}

const traceWithRelationships = runtimeTrace([
  {
    id: 'user-1',
    kind: 'user.submitted',
    lane: 'user',
    label: '帮我找一家附近评分较高而且现在营业的咖啡店',
    status: 'submitted',
    timestamp: at(0),
    messageId: 'agent-main',
  },
  {
    id: 'agent-1',
    kind: 'agent.activity',
    lane: 'agent',
    label: 'Agent 简短回复',
    status: 'complete',
    timestamp: at(1),
    endTimestamp: at(6),
    messageId: 'agent-main',
  },
  {
    id: 'delegate-1',
    kind: 'task.delegated',
    lane: 'task',
    label: '委派搜索任务',
    status: 'active',
    timestamp: at(2),
    taskId: 'task-1',
    originMessageId: 'agent-main',
  },
  {
    id: 'result-1',
    kind: 'task.succeeded',
    lane: 'task',
    label: '搜索任务完成',
    status: 'complete',
    timestamp: at(5),
    taskId: 'task-1',
  },
  {
    id: 'agent-result-1',
    kind: 'agent.activity',
    lane: 'agent',
    label: '基于任务结果回复',
    status: 'complete',
    timestamp: at(6),
    endTimestamp: at(7),
    sourceTaskId: 'task-1',
  },
])

const delegatedEntry: RuntimeTraceEntry = {
  id: 'agent-delegated:agent-origin',
  kind: 'agent.delegated',
  lane: 'agent',
  label: '发起任务',
  status: 'complete',
  timestamp: START,
  endTimestamp: START,
  messageId: 'agent-origin',
}

describe('ReactRuntimePanel', () => {
  it('uses delegated copy only for agent delegation entries', () => {
    expect(getRuntimeEntryStatusLabel(delegatedEntry)).toBe('已发起')
    expect(getRuntimeEntryStatusLabel(traceWithRelationships.entries[1])).toBe('已完成')
    expect(getRuntimeEntryStatusLabel({
      ...traceWithRelationships.entries[1],
      status: 'active',
      endTimestamp: undefined,
    })).toBe('思考中')
  })

  it('derives the real content end without using the minimum track width', () => {
    const contentEndX = getRuntimeContentEndX({
      width: 760,
      playheadX: 80,
      taskContentHeight: 80,
      entries: [{
        entry: traceWithRelationships.entries[0],
        x: 100,
        width: 50,
      }],
      tasks: [{
        task: task(),
        x: 90,
        width: 200,
        axisIndex: 0,
        axisTop: 10,
        contentTop: 23,
      }],
      userGaps: [],
      connectors: [{
        id: 'latest-connector',
        kind: 'result',
        taskId: 'task-1',
        relatedEntryIds: [],
        from: { lane: 'task', x: 310, y: 267 },
        to: { lane: 'agent', x: 310, y: 170 },
      }],
    })

    expect(contentEndX).toBe(310)
  })

  it('initializes short tracks at zero instead of scrolling into blank space', () => {
    expect(getRuntimeScrollTarget({
      clientWidth: 600,
      scrollWidth: 760,
      currentScrollLeft: 0,
      previousContentEndX: 0,
      contentEndX: 300,
      isInitial: true,
    })).toEqual({ shouldScroll: true, left: 0 })
  })

  it('follows content growth only while the previous end remains in view', () => {
    expect(getRuntimeScrollTarget({
      clientWidth: 400,
      scrollWidth: 1000,
      currentScrollLeft: 480,
      previousContentEndX: 900,
      contentEndX: 950,
      isInitial: false,
    })).toEqual({ shouldScroll: true, left: 574 })

    expect(getRuntimeScrollTarget({
      clientWidth: 400,
      scrollWidth: 1000,
      currentScrollLeft: 200,
      previousContentEndX: 900,
      contentEndX: 950,
      isInitial: false,
    })).toEqual({ shouldScroll: false, left: 200 })
  })

  it('reinitializes scroll when runtime content shrinks', () => {
    expect(getRuntimeScrollTarget({
      clientWidth: 400,
      scrollWidth: 760,
      currentScrollLeft: 200,
      previousContentEndX: 2000,
      contentEndX: 32,
      isInitial: false,
    })).toEqual({ shouldScroll: true, left: 0 })
  })

  it('clamps initial and follow targets to the actual scroll range', () => {
    expect(getRuntimeScrollTarget({
      clientWidth: 400,
      scrollWidth: 1000,
      currentScrollLeft: 0,
      previousContentEndX: 0,
      contentEndX: 1200,
      isInitial: true,
    })).toEqual({ shouldScroll: true, left: 600 })
  })

  it('reanchors a live runtime after its viewport narrows', () => {
    expect(getRuntimeResizeScrollTarget({
      clientWidth: 400,
      scrollWidth: 1200,
      currentScrollLeft: 424,
      contentEndX: 1000,
      wasAtLiveEdge: true,
    })).toEqual({ shouldScroll: true, left: 624 })
  })

  it('preserves a valid history position after a runtime resize', () => {
    expect(getRuntimeResizeScrollTarget({
      clientWidth: 400,
      scrollWidth: 1200,
      currentScrollLeft: 160,
      contentEndX: 1000,
      wasAtLiveEdge: false,
    })).toEqual({ shouldScroll: false, left: 160 })
  })

  it('only clamps history when a runtime resize invalidates its position', () => {
    expect(getRuntimeResizeScrollTarget({
      clientWidth: 1000,
      scrollWidth: 1100,
      currentScrollLeft: 240,
      contentEndX: 1000,
      wasAtLiveEdge: false,
    })).toEqual({ shouldScroll: true, left: 100 })
  })

  it('recognizes the horizontal live edge within the existing threshold', () => {
    expect(isRuntimeAtLiveEdge({
      clientWidth: 600,
      currentScrollLeft: 368,
      contentEndX: 1000,
    })).toBe(true)

    expect(isRuntimeAtLiveEdge({
      clientWidth: 600,
      currentScrollLeft: 300,
      contentEndX: 1000,
    })).toBe(false)
  })

  it('recognizes the task live edge within the existing threshold', () => {
    expect(isRuntimeTaskAtLiveEdge({
      clientHeight: 180,
      scrollHeight: 426,
      currentScrollTop: 214,
    })).toBe(true)

    expect(isRuntimeTaskAtLiveEdge({
      clientHeight: 180,
      scrollHeight: 426,
      currentScrollTop: 180,
    })).toBe(false)
  })

  it('follows new task axes only while the previous bottom remains in view', () => {
    expect(getRuntimeTaskScrollTarget({
      clientHeight: 180,
      scrollHeight: 426,
      currentScrollTop: 180,
      previousViewportHeight: 180,
      previousContentHeight: 360,
      isInitial: false,
    })).toEqual({ shouldScroll: true, top: 246 })

    expect(getRuntimeTaskScrollTarget({
      clientHeight: 180,
      scrollHeight: 426,
      currentScrollTop: 80,
      previousViewportHeight: 180,
      previousContentHeight: 360,
      isInitial: false,
    })).toEqual({ shouldScroll: false, top: 80 })
  })

  it('restores task follow at the bottom and clamps after session shrink', () => {
    expect(getRuntimeTaskScrollTarget({
      clientHeight: 180,
      scrollHeight: 492,
      currentScrollTop: 246,
      previousViewportHeight: 180,
      previousContentHeight: 426,
      isInitial: false,
    })).toEqual({ shouldScroll: true, top: 312 })

    expect(getRuntimeTaskScrollTarget({
      clientHeight: 180,
      scrollHeight: 180,
      currentScrollTop: 200,
      previousViewportHeight: 180,
      previousContentHeight: 492,
      isInitial: false,
    })).toEqual({ shouldScroll: true, top: 0 })
  })

  it('preserves a valid user position when task content shrinks', () => {
    expect(getRuntimeTaskScrollTarget({
      clientHeight: 180,
      scrollHeight: 426,
      currentScrollTop: 80,
      previousViewportHeight: 180,
      previousContentHeight: 492,
      isInitial: false,
    })).toEqual({ shouldScroll: false, top: 80 })
  })

  it('follows at the task bottom threshold but preserves positions beyond it', () => {
    expect(getRuntimeTaskScrollTarget({
      clientHeight: 180,
      scrollHeight: 492,
      currentScrollTop: 148,
      previousViewportHeight: 180,
      previousContentHeight: 360,
      isInitial: false,
    })).toEqual({ shouldScroll: true, top: 312 })

    expect(getRuntimeTaskScrollTarget({
      clientHeight: 180,
      scrollHeight: 492,
      currentScrollTop: 147,
      previousViewportHeight: 180,
      previousContentHeight: 360,
      isInitial: false,
    })).toEqual({ shouldScroll: false, top: 147 })
  })

  it('initializes the task viewport at the current bottom', () => {
    expect(getRuntimeTaskScrollTarget({
      clientHeight: 180,
      scrollHeight: 426,
      currentScrollTop: 0,
      previousViewportHeight: Number.POSITIVE_INFINITY,
      previousContentHeight: 426,
      isInitial: true,
    })).toEqual({ shouldScroll: true, top: 246 })
  })

  it('keeps the previous task bottom anchored when the viewport resizes', () => {
    expect(getRuntimeTaskScrollTarget({
      previousViewportHeight: 180,
      previousContentHeight: 426,
      clientHeight: 120,
      scrollHeight: 426,
      currentScrollTop: 246,
      isInitial: false,
    })).toEqual({ shouldScroll: true, top: 306 })

    expect(getRuntimeTaskScrollTarget({
      previousViewportHeight: 120,
      previousContentHeight: 426,
      clientHeight: 180,
      scrollHeight: 426,
      currentScrollTop: 306,
      isInitial: false,
    })).toEqual({ shouldScroll: true, top: 246 })
  })

  it('preserves or clamps an away-from-bottom task viewport after resize', () => {
    expect(getRuntimeTaskScrollTarget({
      previousViewportHeight: 180,
      previousContentHeight: 426,
      clientHeight: 120,
      scrollHeight: 426,
      currentScrollTop: 80,
      isInitial: false,
    })).toEqual({ shouldScroll: false, top: 80 })

    expect(getRuntimeTaskScrollTarget({
      previousViewportHeight: 40,
      previousContentHeight: 426,
      clientHeight: 300,
      scrollHeight: 426,
      currentScrollTop: 200,
      isInitial: false,
    })).toEqual({ shouldScroll: true, top: 126 })
  })

  it('initializes task follow when the viewport is first measured', () => {
    expect(getRuntimeTaskScrollTarget({
      previousViewportHeight: Number.POSITIVE_INFINITY,
      previousContentHeight: 426,
      clientHeight: 180,
      scrollHeight: 426,
      currentScrollTop: 0,
      isInitial: true,
    })).toEqual({ shouldScroll: true, top: 246 })

    expect(getRuntimeTaskScrollTarget({
      previousViewportHeight: Number.POSITIVE_INFINITY,
      previousContentHeight: 80,
      clientHeight: 180,
      scrollHeight: 180,
      currentScrollTop: 0,
      isInitial: true,
    })).toEqual({ shouldScroll: false, top: 0 })
  })

  it('keeps the old bottom through either content-first or resize-first updates', () => {
    const contentFirst = getRuntimeTaskScrollTarget({
      clientHeight: 120,
      scrollHeight: 492,
      currentScrollTop: 246,
      previousViewportHeight: 180,
      previousContentHeight: 426,
      isInitial: false,
    })
    expect(contentFirst).toEqual({ shouldScroll: true, top: 372 })
    expect(getRuntimeTaskScrollTarget({
      previousViewportHeight: 120,
      previousContentHeight: 492,
      clientHeight: 120,
      scrollHeight: 492,
      currentScrollTop: contentFirst.top,
      isInitial: false,
    })).toEqual({ shouldScroll: false, top: 372 })

    const resizeFirst = getRuntimeTaskScrollTarget({
      previousViewportHeight: 180,
      previousContentHeight: 426,
      clientHeight: 120,
      scrollHeight: 492,
      currentScrollTop: 246,
      isInitial: false,
    })
    expect(resizeFirst).toEqual({ shouldScroll: true, top: 372 })
    expect(getRuntimeTaskScrollTarget({
      clientHeight: 120,
      scrollHeight: 492,
      currentScrollTop: resizeFirst.top,
      previousViewportHeight: 120,
      previousContentHeight: 426,
      isInitial: false,
    })).toEqual({ shouldScroll: false, top: 372 })
  })

  it('anchors a threshold-following viewport when content and viewport shrink together', () => {
    expect(getRuntimeTaskScrollTarget({
      clientHeight: 120,
      scrollHeight: 426,
      currentScrollTop: 280,
      previousViewportHeight: 180,
      previousContentHeight: 492,
      isInitial: false,
    })).toEqual({ shouldScroll: true, top: 306 })
  })

  it('preserves an old away position through either shrink update order', () => {
    const contentFirst = getRuntimeTaskScrollTarget({
      clientHeight: 120,
      scrollHeight: 426,
      currentScrollTop: 230,
      previousViewportHeight: 180,
      previousContentHeight: 492,
      isInitial: false,
    })
    expect(contentFirst).toEqual({ shouldScroll: false, top: 230 })
    expect(getRuntimeTaskScrollTarget({
      clientHeight: 120,
      scrollHeight: 426,
      currentScrollTop: contentFirst.top,
      previousViewportHeight: 120,
      previousContentHeight: 426,
      isInitial: false,
    })).toEqual({ shouldScroll: false, top: 230 })

    const resizeFirst = getRuntimeTaskScrollTarget({
      clientHeight: 120,
      scrollHeight: 426,
      currentScrollTop: 230,
      previousViewportHeight: 180,
      previousContentHeight: 492,
      isInitial: false,
    })
    expect(resizeFirst).toEqual({ shouldScroll: false, top: 230 })
    expect(getRuntimeTaskScrollTarget({
      clientHeight: 120,
      scrollHeight: 426,
      currentScrollTop: resizeFirst.top,
      previousViewportHeight: 120,
      previousContentHeight: 492,
      isInitial: false,
    })).toEqual({ shouldScroll: false, top: 230 })
  })

  it('runs the live clock only for unfixed active runtime state', () => {
    const emptyTrace = runtimeTrace([])
    const emptyTasks = taskState([])

    expect(shouldRunRuntimeTimer({
      clockNowMs: START_MS,
      voicePhase: 'listening',
      runtimeTrace: emptyTrace,
      tasks: emptyTasks,
    })).toBe(false)
    expect(shouldRunRuntimeTimer({
      voicePhase: 'idle',
      runtimeTrace: emptyTrace,
      tasks: emptyTasks,
    })).toBe(false)
    expect(shouldRunRuntimeTimer({
      voicePhase: 'mic_pending',
      runtimeTrace: emptyTrace,
      tasks: emptyTasks,
    })).toBe(true)
    expect(shouldRunRuntimeTimer({
      voicePhase: 'idle',
      runtimeTrace: runtimeTrace([{
        ...traceWithRelationships.entries[1],
        status: 'active',
        endTimestamp: undefined,
      }]),
      tasks: emptyTasks,
    })).toBe(true)
    expect(shouldRunRuntimeTimer({
      voicePhase: 'idle',
      runtimeTrace: emptyTrace,
      tasks: taskState([task({ status: 'pending', completedAt: undefined })]),
    })).toBe(true)
  })

  it('moves return-to-live focus to a stable timeline or fullscreen control', () => {
    const timelineFocus = vi.fn()
    const fullscreenCloseFocus = vi.fn()
    const timeline = { focus: timelineFocus }
    const fullscreenClose = { focus: fullscreenCloseFocus }

    focusRuntimeAfterReturn({
      fullscreen: false,
      timeline,
      fullscreenClose,
    })
    expect(timelineFocus).toHaveBeenCalledOnce()
    expect(fullscreenCloseFocus).not.toHaveBeenCalled()

    focusRuntimeAfterReturn({
      fullscreen: true,
      timeline,
      fullscreenClose,
    })
    expect(fullscreenCloseFocus).toHaveBeenCalledOnce()
  })

  it('renders three readable lanes, relationship connectors, and fullscreen control', () => {
    const markup = renderToStaticMarkup(
      <ReactRuntimePanel
        runtimeTrace={traceWithRelationships}
        tasks={taskState([task()])}
        connected
        voicePhase="idle"
        voiceDraft=""
        clockNowMs={START_MS + 10_000}
        onCancelTask={() => undefined}
        onSelectTask={() => undefined}
      />,
    )

    expect(markup).toContain('class="panel runtime-panel"')
    expect(markup).toContain('react runtime')
    expect(markup).toContain('<h2>Agent 如何运行</h2>')
    expect(markup).toContain('用户输入')
    expect(markup).toContain('Agent Runner')
    expect(markup).toContain('TaskManager')
    expect(markup.match(/role="region"/g)).toHaveLength(3)
    expect(markup.match(/data-lane="(?:user|agent|task)"/g)).toHaveLength(3)
    expect(markup).toContain('class="runtime-task-scroll"')
    expect(markup).toContain('class="runtime-timeline-scroll" tabindex="-1"')
    expect(markup).toContain('class="runtime-task-axes"')
    expect(markup).toContain('class="runtime-task-axis"')
    expect(markup).toContain('data-task-axis="task-1"')
    expect(markup).toContain('任务 01 · 搜索附近评分较高的咖啡店')
    expect(markup).toContain('<marker')
    expect(markup).toContain('data-connector="submit"')
    expect(markup).toContain('data-connector="delegate"')
    expect(markup).toContain('data-connector="result"')
    expect(markup).toContain('marker-end="url(#runtime-regular-submit-arrow)"')
    expect(markup).toContain('marker-end="url(#runtime-regular-delegate-arrow)"')
    expect(markup).toContain('marker-end="url(#runtime-regular-result-arrow)"')
    const connectorPaths = Array.from(markup.matchAll(/<path d="([^"]+)"/g))
      .map((match) => match[1])
    expect(connectorPaths).toHaveLength(3)
    expect(connectorPaths.every((path) => path.includes(' C '))).toBe(true)
    expect(connectorPaths.every((path) => !path.includes(' L '))).toBe(true)
    expect(markup).toContain('提交')
    expect(markup).toContain('发起')
    expect(markup).toContain('结果')
    expect(markup).toContain('aria-label="全屏查看运行关系"')
    expect(markup).toContain('搜索附近评分较高的咖啡店')
    expect(markup).toContain('完成')
    expect(markup).toContain('进度 100%')
    expect(markup).toContain('3.0s')
    expect(markup).not.toContain('暂停')
    expect(markup).not.toContain('回放')
  })

  it('renders a delegated agent action with its kind and delegated status', () => {
    const markup = renderToStaticMarkup(
      <ReactRuntimePanel
        runtimeTrace={runtimeTrace([delegatedEntry])}
        tasks={taskState([])}
        connected
        voicePhase="idle"
        voiceDraft=""
        clockNowMs={START_MS}
        onCancelTask={() => undefined}
        onSelectTask={() => undefined}
      />,
    )

    expect(markup).toContain('data-kind="agent.delegated"')
    expect(markup).toContain('发起任务')
    expect(markup).toContain('已发起')
  })

  it('renders one independent axis and native task button per task', () => {
    const markup = renderToStaticMarkup(
      <ReactRuntimePanel
        runtimeTrace={runtimeTrace([])}
        tasks={taskState([
          task(),
          task({
            taskId: 'task-2',
            title: '查询咖啡店营业状态',
            createdAt: at(3),
            startedAt: at(3),
            updatedAt: at(6),
            completedAt: at(6),
          }),
        ])}
        connected
        voicePhase="idle"
        voiceDraft=""
        clockNowMs={START_MS + 10_000}
        onCancelTask={() => undefined}
        onSelectTask={() => undefined}
      />,
    )

    expect(markup.match(/class="runtime-task-axis"/g)).toHaveLength(2)
    expect(markup.match(/role="group"/g)).toHaveLength(2)
    expect(markup.match(/class="runtime-task-block"/g)).toHaveLength(2)
    expect(markup).toContain('data-task-axis="task-1"')
    expect(markup).toContain('data-task-axis="task-2"')
    expect(markup).toContain('任务 01 · 搜索附近评分较高的咖啡店')
    expect(markup).toContain('任务 02 · 查询咖啡店营业状态')
    expect(markup).toContain(
      'aria-label="任务 01：搜索附近评分较高的咖啡店，状态：完成"',
    )
    expect(markup).toContain(
      'aria-label="任务 02：查询咖啡店营业状态，状态：完成"',
    )
  })

  it('renders connection failure and accessible ASR text without claiming a waveform', () => {
    const markup = renderToStaticMarkup(
      <ReactRuntimePanel
        runtimeTrace={runtimeTrace([])}
        tasks={taskState([])}
        connected={false}
        voicePhase="listening"
        voiceDraft="导航去虹桥机场"
        clockNowMs={START_MS}
        onCancelTask={() => undefined}
        onSelectTask={() => undefined}
      />,
    )

    expect(markup).toContain('role="status"')
    expect(markup).toContain('连接异常')
    expect(markup).toContain('ASR 实时输入')
    expect(markup).toContain('导航去虹桥机场')
    expect(markup).toContain('class="runtime-asr-activity" aria-hidden="true"')
    expect(markup.match(/class="runtime-asr-bar"/g)).toHaveLength(5)
    expect(markup).not.toContain('真实波形')
  })

  it('keeps all lanes visible while waiting for the first fact', () => {
    const markup = renderToStaticMarkup(
      <ReactRuntimePanel
        runtimeTrace={runtimeTrace([])}
        tasks={taskState([])}
        connected={null}
        voicePhase="idle"
        voiceDraft=""
        clockNowMs={START_MS}
        onCancelTask={() => undefined}
        onSelectTask={() => undefined}
      />,
    )

    expect(markup.match(/data-lane="(?:user|agent|task)"/g)).toHaveLength(3)
    expect(markup).toContain('react runtime')
    expect(markup).toContain('<h2>Agent 如何运行</h2>')
    expect(markup).toContain('等待用户输入')
    expect(markup).toContain('输入后将展示请求、Agent 与任务的实时关系')
    expect(markup).not.toContain('暂停')
    expect(markup).not.toContain('回放')
  })

  it('uses a real task button, exposes its status, and selects its task id', () => {
    const onSelectTask = vi.fn()
    const onCancelTask = vi.fn()
    const element = RuntimeTaskBlock({
      task: task(),
      left: 32,
      top: 10,
      width: 160,
      nowMs: START_MS + 10_000,
      onCancelTask,
      onHoverTask: () => undefined,
      onFocusTask: () => undefined,
      onSelectTask,
    })

    expect(element.type).toBe('article')
    expect(element.props['data-status']).toBe('success')
    expect(element.props['data-tool-name']).toBe('search_places')
    const [selectButton, completedCancelButton] = element.props.children
    selectButton.props.onClick()
    expect(onSelectTask).toHaveBeenCalledWith('task-1')
    expect(completedCancelButton).toBe(false)

    const runningElement = RuntimeTaskBlock({
      task: task({ status: 'running', completedAt: undefined }),
      left: 32,
      top: 10,
      width: 160,
      nowMs: START_MS + 10_000,
      onCancelTask,
      onHoverTask: () => undefined,
      onFocusTask: () => undefined,
      onSelectTask,
    })
    expect(runningElement.props['data-status']).toBe('running')
    const [, cancelButton] = runningElement.props.children
    expect(cancelButton.props['aria-label']).toBe(
      '取消 搜索附近评分较高的咖啡店',
    )
    expect(cancelButton.props.disabled).toBe(false)
    cancelButton.props.onClick()
    expect(onCancelTask).toHaveBeenCalledWith('task-1')

    const cancellingElement = RuntimeTaskBlock({
      task: task({ status: 'cancelling', completedAt: undefined }),
      left: 32,
      top: 10,
      width: 160,
      nowMs: START_MS + 10_000,
      onCancelTask,
      onHoverTask: () => undefined,
      onFocusTask: () => undefined,
      onSelectTask,
    })
    const [, cancellingButton] = cancellingElement.props.children
    expect(cancellingButton.props['aria-label']).toBe(
      '正在取消 搜索附近评分较高的咖啡店',
    )
    expect(cancellingButton.props.disabled).toBe(true)
  })

  it('keeps task status and accessibility styles behaviorally distinct', () => {
    const css = readFileSync(new URL('../styles.css', import.meta.url), 'utf8')
    const runtimeBlock = css.slice(css.indexOf('/* ReAct runtime relationship */'))
    const reducedMotionBlock = extractCssAtRuleBlock(
      runtimeBlock,
      '@media (prefers-reduced-motion: reduce)',
    )
    const contrastBlock = extractCssAtRuleBlock(
      runtimeBlock,
      '@media (prefers-contrast: more)',
    )
    const titleRule = runtimeBlock.match(
      /(?<! )\.runtime-task-title\s*\{([^}]*)\}/,
    )?.[1]
    const thinkingSheenRule = runtimeBlock.match(
      /\.runtime-entry-agent\[data-status='active'\]::before\s*\{([^}]*)\}/s,
    )?.[1]
    const runningRailRule = runtimeBlock.match(
      /\.runtime-task-block\[data-status='running'\]::before\s*\{([^}]*)\}/s,
    )?.[1]
    const runningEdgeRule = runtimeBlock.match(
      /\.runtime-task-block\[data-status='running'\]::after\s*\{([^}]*)\}/s,
    )?.[1]
    const successRule = runtimeBlock.match(
      /\.runtime-task-block\[data-status='success'\]\s*\{([^}]*)\}/s,
    )?.[1]
    const cancelledRule = runtimeBlock.match(
      /\.runtime-task-block\[data-status='cancelled'\]\s*\{([^}]*)\}/s,
    )?.[1]
    const cancelledTitleRule = runtimeBlock.match(
      /\.runtime-task-block\[data-status='cancelled'\] \.runtime-task-title\s*\{([^}]*)\}/s,
    )?.[1]

    expect(titleRule).toContain('font-size: 10px;')
    expect(titleRule).toContain('line-height: 1.2;')
    expect(successRule).not.toBe(cancelledRule)
    expect(cancelledRule).toContain('background: #fff1f4;')
    expect(cancelledRule).toContain('box-shadow:')
    expect(cancelledTitleRule).toContain('text-decoration: line-through;')
    expect(runtimeBlock).not.toMatch(/\.runtime-task-block::(?:before|after)\s*\{/)
    expect(runtimeBlock).not.toMatch(
      /\.runtime-task-block\[data-status='(?:pending|failed|cancelling|cancelled)'\]::(?:before|after)/,
    )
    expect(thinkingSheenRule).toContain('animation: runtime-thinking-sheen')
    expect(runningRailRule).toContain('animation: runtime-task-rail-flow')
    expect(runningEdgeRule).toContain('right: 0;')
    expect(runtimeBlock).toContain(".runtime-playhead[data-live='true']")
    expect(reducedMotionBlock).toMatch(
      /\.runtime-task-block\[data-status='running'\]::before\s*\{[^}]*animation:\s*none !important;/s,
    )
    expect(contrastBlock).toMatch(
      /\.runtime-task-block\[data-status='running'\]::before\s*\{[^}]*animation:\s*none;/s,
    )
  })
})
