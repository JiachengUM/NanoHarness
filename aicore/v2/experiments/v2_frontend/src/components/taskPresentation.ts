import { isActiveTaskStatus, type TaskProjection } from '../domain/projection'

export function getTaskProgressPresentation(task: TaskProjection) {
  const isActive = isActiveTaskStatus(task.status)
  const progress = Math.min(100, Math.max(0, task.progress ?? 0))
  const isIndeterminate = isActive && progress === 0
  const label = task.status === 'pending'
    ? '等待中…'
    : task.status === 'cancelling'
      ? '取消中…'
      : isIndeterminate
        ? '运行中…'
        : `${Math.round(progress)}%`

  return { isActive, progress, isIndeterminate, label }
}
