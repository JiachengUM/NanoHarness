import { readFileSync } from 'node:fs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import type { SessionResetResult } from './adapters/v2AgentClient'
import App, {
  buildTaskCancelQuery,
  getNextDuplexSurface,
  getServiceStatus,
  getTaskCancelUnavailableFeedback,
  getTaskCancelTargetHint,
  getWorkspaceStatusLabel,
  restoreModeResetFocus,
  runAckFirstSessionReset,
  submitTaskCancellationThroughAgent,
} from './App'
import { extractCssAtRuleBlock } from './test/css'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

type ModeResetFocusTargetStub = {
  isConnected: boolean
  tabIndex: number
  matches: (selector: string) => boolean
  closest: (selector: string) => unknown
  focus: (options?: FocusOptions) => void
}

function createModeResetFocusTarget(
  overrides: Partial<ModeResetFocusTargetStub> = {},
): ModeResetFocusTargetStub {
  return {
    isConnected: true,
    tabIndex: 0,
    matches: (selector) => !selector.includes(':disabled'),
    closest: () => null,
    focus: () => undefined,
    ...overrides,
  }
}

describe('runAckFirstSessionReset', () => {
  it('applies local reset only after the backend ack resolves', async () => {
    const pending = deferred<SessionResetResult>()
    const resetSession = vi.fn(() => pending.promise)
    const onAccepted = vi.fn()

    const operation = runAckFirstSessionReset(
      { resetSession },
      'react',
      onAccepted,
    )

    expect(resetSession).toHaveBeenCalledWith('react')
    expect(onAccepted).not.toHaveBeenCalled()

    pending.resolve({
      agentMode: 'react',
      runtimeProfile: 'react_duplex_shell',
    })
    await operation

    expect(onAccepted).toHaveBeenCalledOnce()
    expect(onAccepted).toHaveBeenCalledWith('react')
  })

  it('does not apply local reset when the backend rejects the command', async () => {
    const pending = deferred<SessionResetResult>()
    const onAccepted = vi.fn()
    const operation = runAckFirstSessionReset(
      { resetSession: () => pending.promise },
      'plact',
      onAccepted,
    )

    pending.reject(new Error('reset rejected'))

    await expect(operation).rejects.toThrow('reset rejected')
    expect(onAccepted).not.toHaveBeenCalled()
  })
})

describe('task cancellation interaction handoff', () => {
  const coffeeTask = {
    taskId: 'task-1',
    toolName: '地点搜索工具',
    title: '地点搜索工具',
    arguments: {
      query: '咖啡店',
      city: '上海',
      show_fields: 'children,business,indoor,navi',
    },
  }
  const restaurantTask = {
    taskId: 'task-2',
    toolName: '地点搜索工具',
    title: '地点搜索工具',
    arguments: {
      query: '安静的餐厅',
      city: '上海',
      show_fields: 'children,business,indoor,navi',
    },
  }

  it('renders cancelling first, then submits an ordinary Agent query', () => {
    const callOrder: string[] = []
    const onRequested = vi.fn(() => callOrder.push('requested'))
    const submitAgentQuery = vi.fn(() => callOrder.push('submitted'))

    const input = submitTaskCancellationThroughAgent(
      coffeeTask,
      [coffeeTask],
      onRequested,
      submitAgentQuery,
      () => '2026-07-17T08:00:00.000Z',
    )

    expect(input).toBe('取消任务：咖啡店')
    expect(callOrder).toEqual(['requested', 'submitted'])
    expect(onRequested).toHaveBeenCalledWith({
      id: 'ui-cancel-request-task-1-2026-07-17T08:00:00.000Z',
      type: 'task.cancel.requested',
      timestamp: '2026-07-17T08:00:00.000Z',
      taskId: 'task-1',
      reason: '用户点击取消，已交给 Agent 处理',
    })
    expect(submitAgentQuery).toHaveBeenCalledWith('取消任务：咖啡店')
  })

  it('uses a raw argument that uniquely identifies one of several same-tool tasks', () => {
    expect(getTaskCancelTargetHint(
      restaurantTask,
      [coffeeTask, restaurantTask],
    )).toBe('安静的餐厅')
    expect(buildTaskCancelQuery(
      restaurantTask,
      [coffeeTask, restaurantTask],
    )).toBe('取消任务：安静的餐厅')
  })

  it('falls back to a unique tool name when no semantic argument is available', () => {
    const webTask = {
      taskId: 'task-web',
      toolName: 'websearch',
      title: 'websearch',
      arguments: {},
    }
    expect(buildTaskCancelQuery(
      webTask,
      [coffeeTask, webTask],
    )).toBe('取消任务：websearch')
  })

  it('keeps unavailable outcomes honest before submitting a query', () => {
    expect(getTaskCancelUnavailableFeedback({
      ...coffeeTask,
      status: 'success',
      progress: 100,
      trace: [],
      createdAt: '2026-07-17T07:59:00.000Z',
      updatedAt: '2026-07-17T08:00:00.000Z',
    })).toEqual({
      message: '任务已经完成，无需取消',
      level: 'info',
    })
    expect(getTaskCancelUnavailableFeedback()).toEqual({
      message: '任务已经结束或不存在',
      level: 'info',
    })
    expect(getTaskCancelUnavailableFeedback({
      ...coffeeTask,
      status: 'cancelled',
      progress: 0,
      trace: [],
      createdAt: '2026-07-17T07:59:00.000Z',
      updatedAt: '2026-07-17T08:00:00.000Z',
    })).toEqual({
      message: '任务已经结束或不存在',
      level: 'info',
    })
  })

  it('keeps Agent cancellation and adds direct native cancellation', () => {
    const source = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8')
    const cancelCallback = source.match(
      /const cancelRuntimeTask[\s\S]*?\n  \}, \[[^\]]+\]\)/,
    )?.[0]

    expect(cancelCallback).toContain('submitTaskCancellationThroughAgent(')
    expect(cancelCallback).toContain('submitTextTurn')
    expect(cancelCallback).toContain("runtimeProfile === 'duplex_native'")
    expect(cancelCallback).toContain('liveClient.cancelTask')
  })
})

describe('mode reset interaction handoff', () => {
  it('waits for React to unlock before restoring the original active element', () => {
    const calls: string[] = []
    let activeElement: ModeResetFocusTargetStub | null = null
    const preferred = createModeResetFocusTarget({
      focus: (options) => {
        calls.push(options?.preventScroll ? 'focus preferred without scroll' : 'focus preferred')
        activeElement = preferred
      },
    })
    const fallback = createModeResetFocusTarget({
      focus: (options) => {
        calls.push(options?.preventScroll ? 'focus fallback without scroll' : 'focus fallback')
        activeElement = fallback
      },
    })
    const environment = {
      isVisible: () => true,
      getActiveElement: () => activeElement,
      isDocumentFallback: () => false,
    }

    expect(restoreModeResetFocus(true, preferred, fallback, environment)).toBe(false)
    expect(calls).toEqual([])

    expect(restoreModeResetFocus(false, preferred, fallback, environment)).toBe(true)
    expect(calls).toEqual(['focus preferred without scroll'])
  })

  it('preserves a valid toolbar focus acquired while reset was pending', () => {
    const calls: string[] = []
    const toastClose = createModeResetFocusTarget()
    const preferred = createModeResetFocusTarget({
      focus: () => calls.push('focus preferred'),
    })
    const fallback = createModeResetFocusTarget({
      focus: () => calls.push('focus fallback'),
    })

    expect(restoreModeResetFocus(false, preferred, fallback, {
      isVisible: () => true,
      getActiveElement: () => toastClose,
      isDocumentFallback: () => false,
    })).toBe(true)
    expect(calls).toEqual([])
  })

  it('restores the original target when reset leaves focus on the document body', () => {
    const calls: string[] = []
    let activeElement: ModeResetFocusTargetStub | null = null
    const body = createModeResetFocusTarget()
    activeElement = body
    const preferred = createModeResetFocusTarget({
      focus: (options) => {
        calls.push(options?.preventScroll ? 'focus preferred without scroll' : 'focus preferred')
        activeElement = preferred
      },
    })

    expect(restoreModeResetFocus(false, preferred, null, {
      isVisible: () => true,
      getActiveElement: () => activeElement,
      isDocumentFallback: (target) => target === body,
    })).toBe(true)
    expect(calls).toEqual(['focus preferred without scroll'])
  })

  it.each([
    [
      'hidden ancestor',
      { closest: (selector: string) => selector.includes('[hidden]') ? {} : null },
      true,
    ],
    [
      'disabled ancestor',
      { closest: (selector: string) => selector.includes(':disabled') ? {} : null },
      true,
    ],
    [
      'inert ancestor',
      { closest: (selector: string) => selector.includes('[inert]') ? {} : null },
      true,
    ],
    ['zero visible area', {}, false],
  ] as const)('restores instead of preserving focus inside a %s', (
    _label,
    currentOverrides,
    currentVisible,
  ) => {
    const calls: string[] = []
    let activeElement: ModeResetFocusTargetStub | null = null
    const current = createModeResetFocusTarget(currentOverrides)
    activeElement = current
    const preferred = createModeResetFocusTarget({
      focus: (options) => {
        calls.push(options?.preventScroll ? 'focus preferred without scroll' : 'focus preferred')
        activeElement = preferred
      },
    })

    expect(restoreModeResetFocus(false, preferred, null, {
      isVisible: (target) => target === current ? currentVisible : true,
      getActiveElement: () => activeElement,
      isDocumentFallback: () => false,
    })).toBe(true)
    expect(calls).toEqual(['focus preferred without scroll'])
  })

  it.each([
    ['disconnected', { isConnected: false }, true],
    ['disabled', { matches: () => true }, true],
    ['not tabbable', { tabIndex: -1 }, true],
    ['inside an inert or hidden subtree', { closest: () => ({}) }, true],
    ['not visibly rendered', {}, false],
  ] as const)('uses the toolbar fallback when the original target is %s', (
    _label,
    overrides,
    preferredVisible,
  ) => {
    const calls: string[] = []
    let activeElement: ModeResetFocusTargetStub | null = null
    const preferred = createModeResetFocusTarget({
      ...overrides,
      focus: () => calls.push('focus invalid preferred'),
    })
    const fallback = createModeResetFocusTarget({
      focus: (options) => {
        calls.push(options?.preventScroll ? 'focus fallback without scroll' : 'focus fallback')
        activeElement = fallback
      },
    })

    expect(restoreModeResetFocus(false, preferred, fallback, {
      isVisible: (target) => target === preferred ? preferredVisible : true,
      getActiveElement: () => activeElement,
      isDocumentFallback: () => false,
    })).toBe(true)
    expect(calls).toEqual(['focus fallback without scroll'])
  })

  it('announces pending reset in the non-inert toolbar and clears it afterward', () => {
    const serviceStatus = getServiceStatus(true)
    expect(getWorkspaceStatusLabel(serviceStatus, true)).toBe('服务可用 · 正在重置会话')
    expect(getWorkspaceStatusLabel(serviceStatus, false)).toBe('服务可用')
  })
})

describe('getServiceStatus', () => {
  it('describes a health check that has not completed', () => {
    expect(getServiceStatus(null)).toEqual({ label: '检测中', tone: 'checking' })
  })

  it('describes an available service', () => {
    expect(getServiceStatus(true)).toEqual({ label: '服务可用', tone: 'available' })
  })

  it('describes an unavailable service', () => {
    expect(getServiceStatus(false)).toEqual({ label: '服务不可用', tone: 'unavailable' })
  })
})

describe('App', () => {
  it('toggles the Duplex foreground between particle and input surfaces', () => {
    expect(getNextDuplexSurface('particle')).toBe('input')
    expect(getNextDuplexSurface('input')).toBe('particle')

    const markup = renderToStaticMarkup(createElement(App))
    expect(markup).toContain('aria-label="切换到输入视图"')
    expect(markup).toContain('data-surface="particle"')
    expect(markup).toContain('Duplex 粒子状态：静默待机')
    expect(markup).not.toContain('aria-label="live agent input"')
  })

  it('hides TaskBoard and opens the ReAct runtime in the initial layout', () => {
    const markup = renderToStaticMarkup(createElement(App))

    expect(markup).not.toContain('task manager')
    expect(markup).not.toContain('plan dag')
    expect(markup).toContain('react runtime')
  })

  it('keeps typed submission explicit while voice events flow through reducer dispatch', () => {
    const source = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8')
    const voiceHookSource = readFileSync(
      new URL('./voice/useVoiceSession.ts', import.meta.url),
      'utf8',
    )
    const voiceLifecycleSource = readFileSync(
      new URL('./voice/voiceLifecycle.ts', import.meta.url),
      'utf8',
    )

    expect(source.match(/type:\s*'startConversation'/g)).toHaveLength(1)
    expect(source).toMatch(/useVoiceSession\(\{[\s\S]*?dispatch,[\s\S]*?\}\)/)
    expect(source).toContain('startTextTurnVoiceOutput({ startAgentRun })')
    expect(source).toContain('acceptedPlaybackMessageId: state.acceptedPlaybackMessageId')
    expect(source).toContain('acceptedPlaybackRevision: state.acceptedPlaybackRevision')
    expect(source).toContain('readVoiceAcoustics={readVoiceAcoustics}')
    expect(source).toContain('transcript={latestVoiceTranscript}')
    expect(voiceHookSource).toContain('dispatchConsoleAction: (action) => dispatch(action)')
    expect(voiceHookSource).toContain('applyAcceptedPlaybackProjection({')
    expect(voiceHookSource).toContain('nextVoiceTranscript(current, event)')
    expect(voiceHookSource).not.toContain(
      'setPlaybackAssistantMessageId(assistantMessageId)',
    )
    expect(voiceHookSource).not.toContain('startConversation')
    expect(voiceHookSource).not.toContain('liveClient.sendVoiceTextQuery(input)')
    expect(voiceLifecycleSource).not.toContain('startConversation')
  })

  it('renders the global workspace toolbar and dual-stage shell', () => {
    const markup = renderToStaticMarkup(createElement(App))

    expect(markup).toContain('class="workspace-toolbar"')
    expect(markup).toContain('<p class="eyebrow">AICORE · V2</p>')
    expect(markup).toContain('<h1>Agent Console</h1>')
    expect(markup).toContain('对话、计划与运行证据')
    expect(markup).not.toContain('Agent Workspace')
    expect(markup).not.toContain('对话执行与能力证据')
    expect(markup).toContain('aria-label="Agent 模式"')
    expect(markup).toContain('aria-pressed="true">ReAct')
    expect(markup).not.toContain('>PlAct</button>')
    expect(markup).toContain('aria-label="对话方式"')
    expect(markup).toContain('aria-pressed="false">V2 Agent 语音问答</button>')
    expect(markup).toContain('aria-pressed="true">原生 Duplex</button>')
    expect(markup).toContain('新建对话')
    expect(markup).toContain('class="console-stage"')
  })

  it('makes the stage and inspector non-interactive while a mode reset is pending', () => {
    const source = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8')
    const stage = source.match(
      /<div\s+className=\{`console-stage[\s\S]*?<\/div>\s+<InspectorDrawer/,
    )?.[0]

    expect(stage).toBeDefined()
    expect(stage).toContain('inert={modeResetting}')
    expect(stage).toContain('aria-busy={modeResetting || undefined}')
    expect(source).toMatch(
      /<InspectorDrawer\s+state=\{state\}\s+interactionDisabled=\{modeResetting\}/,
    )
  })

  it('captures reset focus before locking and restores it from a post-render effect', () => {
    const source = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8')
    const captureIndex = source.indexOf('const activeElement = document.activeElement')
    const retainIndex = source.indexOf('modeResetFocusTargetsRef.current = {')
    const lockIndex = source.indexOf('setModeResetting(true)')

    expect(captureIndex).toBeGreaterThanOrEqual(0)
    expect(retainIndex).toBeGreaterThan(captureIndex)
    expect(lockIndex).toBeGreaterThan(retainIndex)
    expect(source).toMatch(
      /useEffect\(\(\) => \{[\s\S]*?restoreModeResetFocus\(\s*modeResetting,[\s\S]*?\}, \[modeResetting\]\)/,
    )
    expect(source).toContain('resetSessionProjection(mode, event.currentTarget)')
    expect(source).toContain('newConversation(event.currentTarget)')
  })

  it('keeps the pending reset announcement in the toolbar live region', () => {
    const source = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8')
    const toolbar = source.match(
      /<header className="workspace-toolbar">[\s\S]*?<\/header>/,
    )?.[0]

    expect(toolbar).toBeDefined()
    expect(toolbar).toContain('role="status"')
    expect(toolbar).toContain('aria-live="polite"')
    expect(toolbar).toContain('getWorkspaceStatusLabel(serviceStatus, modeResetting)')
  })

  it('rejects reset focus targets hidden by zero opacity on themselves or ancestors', () => {
    const source = readFileSync(new URL('./App.tsx', import.meta.url), 'utf8')
    const visibilityHelper = source.match(
      /function isModeResetFocusTargetVisible\([\s\S]*?\n\}/,
    )?.[0]

    expect(visibilityHelper).toBeDefined()
    expect(visibilityHelper).toContain('const opacity = Number.parseFloat(style.opacity)')
    expect(visibilityHelper).toContain('Number.isFinite(opacity) && opacity === 0')
    expect(visibilityHelper).toContain('element = element.parentElement')
  })

  it('preserves visible focus and accessible material fallbacks', () => {
    const css = readFileSync(new URL('./styles.css', import.meta.url), 'utf8')
    const reducedMotionBlock = extractCssAtRuleBlock(
      css,
      '@media (prefers-reduced-motion: reduce)',
    )
    const reducedTransparencyBlock = extractCssAtRuleBlock(
      css,
      '@media (prefers-reduced-transparency: reduce)',
    )
    const contrastBlock = extractCssAtRuleBlock(
      css,
      '@media (prefers-contrast: more)',
    )

    expect(css).toMatch(/button:focus-visible\s*\{[^}]*outline:/s)
    expect(reducedMotionBlock).toContain('animation: none !important;')
    expect(reducedTransparencyBlock).toMatch(
      /\.workspace-toolbar,\s*\.panel,\s*\.planner-rail\s*\{[^}]*backdrop-filter:\s*none;/s,
    )
    expect(contrastBlock).toMatch(
      /\.workspace-toolbar,\s*\.panel,\s*\.planner-rail\s*\{[^}]*backdrop-filter:\s*none;/s,
    )
    expect(contrastBlock).toContain('border-width: 2px;')
  })
})
