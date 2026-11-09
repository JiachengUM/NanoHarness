import { readFileSync } from 'node:fs'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { TaskProjectionState } from '../domain/projection'
import { TaskBoard } from './TaskBoard'

const timestamp = '2026-06-16T10:00:00.000Z'

function createTasks(): TaskProjectionState {
  return {
    byId: {
      'weather-task': {
        taskId: 'weather-task',
        toolName: 'weather_search',
        title: 'weather_search',
        arguments: {},
        status: 'success',
        progress: 100,
        trace: ['天气查询完成'],
        result: {},
        createdAt: timestamp,
        updatedAt: timestamp,
        completedAt: timestamp,
      },
    },
    order: ['weather-task'],
  }
}

describe('TaskBoard', () => {
  it('shows explicit empty-state titles for active and archived tasks', () => {
    const markup = renderToStaticMarkup(
      <TaskBoard
        tasks={{ byId: {}, order: [] }}
        onCancel={() => undefined}
        onSelect={() => undefined}
      />,
    )

    expect(markup).toContain('暂无进行中任务')
    expect(markup).toContain('暂无历史任务')
  })

  it('renders archived tasks as compact history rows', () => {
    const markup = renderToStaticMarkup(
      <TaskBoard
        tasks={createTasks()}
        onCancel={() => undefined}
        onSelect={() => undefined}
      />,
    )

    expect(markup).toContain('weather_search')
    expect(markup).toContain('完成')
  })

  it('keeps backend task progress for active ReAct tools', () => {
    const tasks = createTasks()
    tasks.byId['weather-task'] = {
      ...tasks.byId['weather-task'],
      status: 'running',
      progress: 55,
      completedAt: undefined,
    }
    const markup = renderToStaticMarkup(
      <TaskBoard
        tasks={tasks}
        onCancel={() => undefined}
        onSelect={() => undefined}
      />,
    )

    expect(markup).toContain('55%')
    expect(markup).toContain('progress-track active compact')
  })

  it('shows pending and cancelling tasks as active with fixed Chinese states', () => {
    const tasks = createTasks()
    tasks.byId = {
      pending: {
        ...tasks.byId['weather-task'],
        taskId: 'pending',
        title: '等待任务',
        status: 'pending',
        progress: 0,
        completedAt: undefined,
      },
      running: {
        ...tasks.byId['weather-task'],
        taskId: 'running',
        title: '运行任务',
        status: 'running',
        progress: 55,
        completedAt: undefined,
      },
      cancelling: {
        ...tasks.byId['weather-task'],
        taskId: 'cancelling',
        title: '取消任务',
        status: 'cancelling',
        progress: 0,
        completedAt: undefined,
      },
    }
    tasks.order = ['pending', 'running', 'cancelling']

    const markup = renderToStaticMarkup(
      <TaskBoard
        tasks={tasks}
        onCancel={() => undefined}
        onSelect={() => undefined}
      />,
    )

    expect(markup).toContain('等待中…')
    expect(markup).toContain('55%')
    expect(markup).toContain('取消中…')
    expect(markup).not.toContain('>cancelling<')

    const pendingButton = markup.match(/<button[^>]+aria-label="取消 等待任务"[^>]*>/)?.[0]
    const cancellingButton = markup.match(/<button[^>]+aria-label="取消 取消任务"[^>]*>/)?.[0]
    expect(pendingButton).toBeDefined()
    expect(pendingButton).not.toContain('disabled')
    expect(cancellingButton).toContain('disabled')
  })

  it('uses a native selection button with a sibling cancel button', () => {
    const tasks = createTasks()
    tasks.byId['weather-task'] = {
      ...tasks.byId['weather-task'],
      status: 'running',
      progress: 55,
      completedAt: undefined,
    }
    const markup = renderToStaticMarkup(
      <TaskBoard
        tasks={tasks}
        onCancel={() => undefined}
        onSelect={() => undefined}
      />,
    )

    const weatherCard = markup.match(
      /<article[^>]+data-status="running"[\s\S]*?<\/article>/,
    )?.[0]
    expect(weatherCard).toBeDefined()
    expect(weatherCard).not.toContain('role="button"')
    expect(weatherCard).not.toContain('tabindex="0"')

    const selectionButton = weatherCard?.match(
      /<button[^>]+class="task-card-select"[\s\S]*?<\/button>/,
    )?.[0]
    expect(selectionButton).toBeDefined()
    expect(selectionButton).toContain('type="button"')
    expect(selectionButton).toContain('aria-label="查看 weather_search 详情"')
    expect(selectionButton?.match(/<button/g)).toHaveLength(1)
    expect(selectionButton).not.toContain('<div')

    const selectionEnd = weatherCard?.indexOf('</button>') ?? -1
    const cancelStart = weatherCard?.indexOf('class="task-compact-cancel"') ?? -1
    expect(selectionEnd).toBeGreaterThan(-1)
    expect(cancelStart).toBeGreaterThan(selectionEnd)
  })

  it('gives the selection button the card hit area and keeps cancel touchable', () => {
    const css = readFileSync(new URL('../styles.css', import.meta.url), 'utf8')
    const cardRule = css.match(/\.task-card \{[\s\S]*?\}/)?.[0]
    const selectRule = css.match(/\.task-card-select \{[\s\S]*?\}/)?.[0]
    const cancelRule = css.match(/\.task-compact-cancel \{[\s\S]*?\}/)?.[0]

    expect(cardRule).toContain('position: relative;')
    expect(selectRule).toContain('width: 100%;')
    expect(cancelRule).toContain('position: absolute;')
  })
})
