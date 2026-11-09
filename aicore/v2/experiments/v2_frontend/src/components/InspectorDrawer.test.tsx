import { readFileSync } from 'node:fs'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { initialConsoleState } from '../app/consoleReducer'
import type { TaskProjection } from '../domain/projection'
import {
  createInspectorLifecycleState,
  InspectorDrawer,
  reduceInspectorLifecycle,
  resolveInspectorExternalFocusTarget,
  restoreInspectorCloseFocus,
  runInspectorClose,
  shouldFinalizeInspectorExit,
  subscribeToInspectorFocusIn,
} from './InspectorDrawer'

type FocusTargetStub = {
  isConnected: boolean
  tabIndex: number
  matches: (selector: string) => boolean
  closest: (selector: string) => unknown
  focus: (options?: FocusOptions) => void
  blur: () => void
}

type FocusEnvironmentStub = {
  isVisible: (target: FocusTargetStub) => boolean
  getActiveElement: () => unknown
  isInsideDrawer: (target: unknown) => boolean
}

function createFocusTargetStub(
  calls: string[],
  overrides: Partial<FocusTargetStub> = {},
): FocusTargetStub {
  return {
    isConnected: true,
    tabIndex: 0,
    matches: (selector) => selector !== ':disabled',
    closest: () => null,
    focus: (options) => calls.push(
      options?.preventScroll ? 'focus target without scroll' : 'focus target',
    ),
    blur: () => calls.push('blur target'),
    ...overrides,
  }
}

function createTask(): TaskProjection {
  return {
    taskId: 'task-1',
    toolName: '地点搜索工具',
    title: '地点搜索工具',
    arguments: {},
    status: 'cancelling',
    progress: 0,
    trace: [],
    createdAt: '2026-06-16T10:00:00.000Z',
    updatedAt: '2026-06-16T10:00:01.000Z',
  }
}

describe('InspectorDrawer', () => {
  it('treats cancelling as active and does not expose the raw English state', () => {
    const state = initialConsoleState()
    state.selectedTaskId = 'task-1'
    state.tasks = {
      byId: {
        'task-1': createTask(),
      },
      order: ['task-1'],
    }

    const markup = renderToStaticMarkup(
      <InspectorDrawer state={state} onClose={() => undefined} />,
    )

    expect(markup).toContain('取消中…')
    expect(markup).toContain('progress-track active indeterminate')
    expect(markup).not.toContain('>cancelling<')
  })

  it('stays mounted but inert and hidden when closed', () => {
    const markup = renderToStaticMarkup(
      <InspectorDrawer state={initialConsoleState()} onClose={() => undefined} />,
    )
    const aside = markup.match(/<aside[^>]*>/)?.[0]

    expect(aside).toBeDefined()
    if (!aside) return
    expect(aside).toContain('class="inspector-drawer"')
    expect(aside).toContain('aria-hidden="true"')
    expect(aside).toMatch(/\sinert(?:="")?/)
    expect(aside).toContain('aria-label="Console State"')
    expect(aside).not.toContain('role="dialog"')
    expect(aside).not.toContain('aria-modal')
    expect(markup).toContain('Console State')
    expect(markup).toContain('aria-label="关闭 Console State"')
  })

  it('opens as a non-modal complementary panel without inert', () => {
    const state = initialConsoleState()
    state.selectedTaskId = 'task-1'
    state.tasks = { byId: { 'task-1': createTask() }, order: ['task-1'] }

    const markup = renderToStaticMarkup(
      <InspectorDrawer state={state} onClose={() => undefined} />,
    )
    const aside = markup.match(/<aside[^>]*>/)?.[0]

    expect(aside).toContain('class="inspector-drawer is-open"')
    expect(aside).toContain('aria-label="任务详情"')
    expect(aside).not.toContain('aria-hidden="true"')
    expect(aside).not.toMatch(/\sinert(?:=|\s|>)/)
    expect(aside).not.toContain('role="dialog"')
    expect(aside).not.toContain('aria-modal')
    expect(markup).toContain('aria-label="关闭任务详情"')
  })

  it('stays visibly open but becomes inert while interactions are disabled', () => {
    const state = initialConsoleState()
    state.selectedTaskId = 'task-1'
    state.tasks = { byId: { 'task-1': createTask() }, order: ['task-1'] }

    const markup = renderToStaticMarkup(
      <InspectorDrawer
        state={state}
        interactionDisabled
        onClose={() => undefined}
      />,
    )
    const aside = markup.match(/<aside[^>]*>/)?.[0]

    expect(aside).toContain('class="inspector-drawer is-open"')
    expect(aside).toMatch(/\sinert(?:="")?/)
    expect(aside).toContain('aria-busy="true"')
    expect(aside).not.toContain('aria-hidden="true"')
  })

  it('resets raw state and restores focus before notifying the parent to close', () => {
    const calls: string[] = []
    runInspectorClose(
      () => calls.push('reset raw'),
      () => calls.push('restore focus'),
      () => calls.push('close'),
    )

    expect(calls).toEqual(['reset raw', 'restore focus', 'close'])
  })

  it('restores focus to a connected focusable trigger outside the drawer', () => {
    const calls: string[] = []
    let activeElement: unknown
    let target: FocusTargetStub
    target = createFocusTargetStub(calls, {
      focus: (options) => {
        calls.push(options?.preventScroll ? 'focus target without scroll' : 'focus target')
        activeElement = target
      },
    })
    const closeButton = createFocusTargetStub(calls, {
      blur: () => calls.push('blur close'),
    })
    const environment: FocusEnvironmentStub = {
      isVisible: () => true,
      getActiveElement: () => activeElement,
      isInsideDrawer: () => false,
    }

    restoreInspectorCloseFocus(target, closeButton, false, environment)

    expect(calls).toEqual(['focus target without scroll'])
  })

  it.each([
    ['disconnected', { isConnected: false }, false],
    ['inside an inert subtree', { closest: () => ({}) }, false],
    ['inside the drawer', {}, true],
    ['not focusable', { matches: () => false }, false],
  ] as const)('blurs the close button when the trigger is %s', (_label, overrides, isInsideDrawer) => {
    const calls: string[] = []
    const target = createFocusTargetStub(calls, overrides)
    const closeButton = createFocusTargetStub(calls, {
      blur: () => calls.push('blur close'),
    })

    restoreInspectorCloseFocus(target, closeButton, isInsideDrawer, {
      isVisible: () => true,
      getActiveElement: () => target,
      isInsideDrawer: () => false,
    })

    expect(calls).toEqual(['blur close'])
  })

  it.each([
    {
      label: 'disabled even with tabindex 0',
      overrides: { matches: (selector: string) => selector === ':disabled' || selector.includes(',') },
      isVisible: true,
    },
    { label: 'tabindex -2', overrides: { tabIndex: -2 }, isVisible: true },
    {
      label: 'inside a hidden subtree',
      overrides: { closest: (selector: string) => selector.includes('[hidden]') ? {} : null },
      isVisible: true,
    },
    {
      label: 'inside an aria-hidden subtree',
      overrides: {
        closest: (selector: string) => selector.includes('[aria-hidden="true"]') ? {} : null,
      },
      isVisible: true,
    },
    {
      label: 'inside an inert subtree',
      overrides: { closest: (selector: string) => selector.includes('[inert]') ? {} : null },
      isVisible: true,
    },
    { label: 'not visibly rendered', overrides: {}, isVisible: false },
  ])('rejects a $label return target', ({ overrides, isVisible }) => {
    const calls: string[] = []
    const target = createFocusTargetStub(calls, overrides)
    const closeButton = createFocusTargetStub(calls, {
      blur: () => calls.push('blur close'),
    })

    restoreInspectorCloseFocus(target, closeButton, false, {
      isVisible: () => isVisible,
      getActiveElement: () => target,
      isInsideDrawer: () => false,
    })

    expect(calls).toEqual(['blur close'])
  })

  it.each([
    ['does not move focus', false],
    ['throws', true],
  ] as const)('blurs the close button when target focus %s', (_label, shouldThrow) => {
    const calls: string[] = []
    const closeButton = createFocusTargetStub(calls, {
      blur: () => calls.push('blur close'),
    })
    const rawToggle = createFocusTargetStub(calls, {
      blur: () => calls.push('blur raw toggle'),
    })
    const target = createFocusTargetStub(calls, {
      focus: (options) => {
        calls.push(options?.preventScroll ? 'focus target without scroll' : 'focus target')
        if (shouldThrow) throw new Error('focus failed')
      },
    })

    expect(() => restoreInspectorCloseFocus(target, closeButton, false, {
      isVisible: () => true,
      getActiveElement: () => rawToggle,
      isInsideDrawer: (candidate) => candidate === rawToggle,
    })).not.toThrow()
    expect(calls).toEqual(['focus target without scroll', 'blur raw toggle'])
  })

  it('blurs the active raw toggle when the saved return target is invalid', () => {
    const calls: string[] = []
    const target = createFocusTargetStub(calls, { isConnected: false })
    const closeButton = createFocusTargetStub(calls, {
      blur: () => calls.push('blur close'),
    })
    const rawToggle = createFocusTargetStub(calls, {
      blur: () => calls.push('blur raw toggle'),
    })

    restoreInspectorCloseFocus(target, closeButton, false, {
      isVisible: () => true,
      getActiveElement: () => rawToggle,
      isInsideDrawer: (candidate) => candidate === rawToggle,
    })

    expect(calls).toEqual(['blur raw toggle'])
  })

  it('does not blur an external active element when focus restoration fails', () => {
    const calls: string[] = []
    const target = createFocusTargetStub(calls, { isConnected: false })
    const closeButton = createFocusTargetStub(calls, {
      blur: () => calls.push('blur close'),
    })
    const externalActive = createFocusTargetStub(calls, {
      blur: () => calls.push('blur external'),
    })

    restoreInspectorCloseFocus(target, closeButton, false, {
      isVisible: () => true,
      getActiveElement: () => externalActive,
      isInsideDrawer: () => false,
    })

    expect(calls).toEqual(['blur close'])
  })

  it('tracks the latest valid external focus while open and cleans up repeated subscriptions', () => {
    type FocusInListener = (event: { target: unknown }) => void
    const listeners = new Set<FocusInListener>()
    const subscribe = (captureTarget: (target: unknown) => void) => (
      subscribeToInspectorFocusIn(
        (listener) => listeners.add(listener),
        (listener) => listeners.delete(listener),
        captureTarget,
      )
    )
    const calls: string[] = []
    const taskA = createFocusTargetStub(calls)
    const taskB = createFocusTargetStub(calls)
    const closeButton = createFocusTargetStub(calls)
    let latestTarget: FocusTargetStub | null = taskA
    const captureTarget = (candidate: unknown) => {
      latestTarget = resolveInspectorExternalFocusTarget(
        latestTarget,
        candidate as FocusTargetStub,
        candidate === closeButton,
        () => true,
      )
    }

    const firstCleanup = subscribe(captureTarget)
    expect(listeners.size).toBe(1)
    firstCleanup()
    expect(listeners.size).toBe(0)

    const secondCleanup = subscribe(captureTarget)
    expect(listeners.size).toBe(1)
    listeners.forEach((listener) => listener({ target: taskB }))
    listeners.forEach((listener) => listener({ target: closeButton }))
    expect(latestTarget).toBe(taskB)
    secondCleanup()
    expect(listeners.size).toBe(0)
  })

  it('wires external focus tracking, visibility checks, cleanup, and confirmed restore into the drawer', () => {
    const source = readFileSync(new URL('./InspectorDrawer.tsx', import.meta.url), 'utf8')

    expect(source).toContain('const drawerRef = useRef<HTMLElement | null>(null)')
    expect(source).toContain('const closeButtonRef = useRef<HTMLButtonElement | null>(null)')
    expect(source).toContain('const returnFocusTargetRef = useRef<HTMLElement | null>(null)')
    expect(source).not.toContain('previousIsOpenRef')
    expect(source).toContain('if (!isOpen) return undefined')
    expect(source).toContain('const activeElement = document.activeElement')
    expect(source).toContain('activeElement instanceof HTMLElement')
    expect(source).toContain('resolveInspectorExternalFocusTarget(')
    expect(source).toContain('return subscribeToInspectorFocusIn(')
    expect(source).toContain("document.addEventListener('focusin', listener)")
    expect(source).toContain("document.removeEventListener('focusin', listener)")
    expect(source).toContain('function isInspectorFocusTargetVisible(')
    expect(source).toContain('window.getComputedStyle(')
    expect(source).toContain('getClientRects().length > 0')
    expect(source).toContain('ref={drawerRef}')
    expect(source).toContain('ref={closeButtonRef}')
    expect(source).toMatch(
      /onClick=\{\(\) => runInspectorClose\([\s\S]*?restoreInspectorCloseFocus\([\s\S]*?onClose/,
    )
    expect(source).toContain('isVisible: isInspectorFocusTargetVisible')
    expect(source).toContain('getActiveElement: () => document.activeElement')
    expect(source).toContain('isInsideDrawer: (target) => (')
    expect(source).toContain('target instanceof Node')
  })

  it('resets raw on external close and releases retained content after exit', () => {
    const task = createTask()
    const opened = createInspectorLifecycleState(true, task)
    const rawExpanded = reduceInspectorLifecycle(opened, { type: 'toggleRaw' })
    expect(rawExpanded.showRaw).toBe(true)

    const externallyClosed = reduceInspectorLifecycle(rawExpanded, {
      type: 'sync',
      isOpen: false,
      selectedTask: undefined,
    })
    expect(externallyClosed.showRaw).toBe(false)
    expect(externallyClosed.retainedTask).toBe(task)

    const exitFinished = reduceInspectorLifecycle(externallyClosed, {
      type: 'exitTransitionEnd',
    })
    expect(exitFinished.retainedTask).toBeUndefined()
  })

  it('does not let a stale exit event clear content after a quick reopen', () => {
    const previousTask = createTask()
    const nextTask = { ...previousTask, taskId: 'task-2', title: '天气查询工具' }
    const closed = reduceInspectorLifecycle(
      createInspectorLifecycleState(true, previousTask),
      {
        type: 'sync',
        isOpen: false,
        selectedTask: undefined,
      },
    )
    const reopened = reduceInspectorLifecycle(closed, {
      type: 'sync',
      isOpen: true,
      selectedTask: nextTask,
    })

    expect(reopened.showRaw).toBe(false)
    expect(shouldFinalizeInspectorExit(true, true, 'transform')).toBe(false)
    expect(shouldFinalizeInspectorExit(false, false, 'transform')).toBe(false)
    expect(shouldFinalizeInspectorExit(false, true, 'opacity')).toBe(false)
    expect(shouldFinalizeInspectorExit(false, true, 'transform')).toBe(true)
    expect(
      reduceInspectorLifecycle(reopened, { type: 'exitTransitionEnd' }).retainedTask,
    ).toBe(nextTask)

  })

  it('positions the non-modal drawer from the shared toolbar geometry with an exit transition', () => {
    const css = readFileSync(new URL('../styles.css', import.meta.url), 'utf8')
    const drawerRule = css.match(
      /\.inspector-drawer \{\s*position: fixed;[\s\S]*?\}/,
    )?.[0]

    expect(drawerRule).toContain(
      'top: calc(var(--shell-top-padding) + var(--toolbar-height) + var(--stage-gap) + var(--inspector-clearance));',
    )
    expect(drawerRule).toContain('visibility: hidden;')
    expect(drawerRule).toContain('opacity: 0;')
    expect(drawerRule).toContain('transform: translateX(')
    expect(drawerRule).toContain('transition:')
    expect(css).toContain('.inspector-drawer.is-open')
  })
})
