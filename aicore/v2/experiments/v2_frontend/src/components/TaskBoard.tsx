import { useEffect, useState } from 'react'
import {
  canCancelTask,
  formatTaskDuration,
  getActiveTaskList,
  getArchivedTaskList,
  getTaskDurationMs,
  type TaskProjection,
  type TaskProjectionState,
} from '../domain/projection'
import { getTaskProgressPresentation } from './taskPresentation'

type TaskBoardProps = {
  tasks: TaskProjectionState
  onCancel: (taskId: string) => void
  onSelect: (taskId: string) => void
}

const TASK_TIMER_INTERVAL_MS = 1000

const ARCHIVED_STATUS_LABELS: Record<string, string> = {
  success: '完成',
  failed: '失败',
  cancelled: '已取消',
}

export function TaskBoard({
  tasks,
  onCancel,
  onSelect,
}: TaskBoardProps) {
  const activeTasks = getActiveTaskList(tasks)
  const archivedTasks = getArchivedTaskList(tasks)
  const [nowMs, setNowMs] = useState(() => Date.now())

  useEffect(() => {
    if (activeTasks.length === 0) {
      return undefined
    }

    setNowMs(Date.now())
    const intervalId = window.setInterval(() => {
      setNowMs(Date.now())
    }, TASK_TIMER_INTERVAL_MS)

    return () => window.clearInterval(intervalId)
  }, [activeTasks.length])

  return (
    <section className="panel task-board">
      <header className="panel-header compact">
        <div>
          <p className="eyebrow">task manager</p>
          <h2>后台任务</h2>
        </div>
        {activeTasks.length > 0 && (
          <span className="active-task-hint">Agent 感知 {activeTasks.length} 个活跃任务</span>
        )}
      </header>
      <div className="task-board-columns">
        <TaskColumn
          title="进行中"
          emptyTitle="暂无进行中任务"
          emptyText="运行中的任务会出现在这里。"
          tasks={activeTasks}
          nowMs={nowMs}
          onCancel={onCancel}
          onSelect={onSelect}
        />
        <TaskColumn
          title="历史归档"
          emptyTitle="暂无历史任务"
          emptyText="已完成任务会自动归档到这里。"
          tasks={archivedTasks}
          nowMs={nowMs}
          onCancel={onCancel}
          onSelect={onSelect}
        />
      </div>
    </section>
  )
}

type TaskColumnProps = {
  title: string
  emptyTitle: string
  emptyText: string
  tasks: TaskProjection[]
  nowMs: number
  onCancel: (taskId: string) => void
  onSelect: (taskId: string) => void
}

function TaskColumn({
  title,
  emptyTitle,
  emptyText,
  tasks,
  nowMs,
  onCancel,
  onSelect,
}: TaskColumnProps) {
  return (
    <section className="task-column" aria-label={title}>
      <div className="task-column-header">
        <h3>{title}</h3>
        <span>{tasks.length}</span>
      </div>
      <div className="task-list">
        {tasks.length === 0 ? (
          <div className="empty-copy task-empty">
            <strong>{emptyTitle}</strong>
            <span>{emptyText}</span>
          </div>
        ) : (
          tasks.map((task) => (
            <TaskCard
              key={task.taskId}
              task={task}
              nowMs={nowMs}
              onCancel={onCancel}
              onSelect={onSelect}
            />
          ))
        )}
      </div>
    </section>
  )
}

type TaskCardProps = {
  task: TaskProjection
  nowMs: number
  onCancel: (taskId: string) => void
  onSelect: (taskId: string) => void
}

function TaskCard({
  task,
  nowMs,
  onCancel,
  onSelect,
}: TaskCardProps) {
  const { isActive, progress, isIndeterminate, label: progressLabel } =
    getTaskProgressPresentation(task)
  const durationText = formatTaskDuration(getTaskDurationMs(task, nowMs))
  const latestTrace = task.trace.at(-1) ?? (isActive ? '等待任务事件' : '—')

  // Both active and archived tasks render as compact rows to maximize density.
  // Full formatted detail + raw JSON lives in the inspector drawer (opened via the row).
  return (
    <article
      className={`task-card task-card-compact${isActive ? ' is-active' : ''}`}
      data-status={task.status}
      data-tool-name={task.toolName}
    >
      <button
        className="task-card-select"
        type="button"
        aria-label={`查看 ${task.title} 详情`}
        onClick={() => onSelect(task.taskId)}
      >
        <span className="task-compact-head">
          <span className="task-compact-status" aria-hidden="true" />
          <span className="task-compact-title" title={task.title}>
            {task.title}
          </span>
          {!isActive && (
            <span className="task-compact-state" data-status={task.status}>
              {ARCHIVED_STATUS_LABELS[task.status] ?? task.status}
            </span>
          )}
          {isActive && (
            <span className="task-progress-label">
              {progressLabel}
            </span>
          )}
        </span>
        {isActive && (
          <span
            className={`progress-track active compact${isIndeterminate ? ' indeterminate' : ''}`}
          >
            <span style={isIndeterminate ? undefined : { width: `${progress}%` }} />
          </span>
        )}
        <span className="task-compact-foot">
          <span className="task-compact-trace" title={latestTrace}>
            {latestTrace}
          </span>
          <span className="task-compact-duration">{durationText}</span>
        </span>
      </button>
      {isActive && (
        <button
          className="task-compact-cancel"
          type="button"
          aria-label={`取消 ${task.title}`}
          title="取消任务"
          disabled={!canCancelTask(task)}
          onClick={() => onCancel(task.taskId)}
        >
          ×
        </button>
      )}
    </article>
  )
}
