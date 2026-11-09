import type { TaskStatus } from '../domain/events'
import { isActiveTaskStatus } from '../domain/projection'

const labels: Record<TaskStatus, string> = {
  pending: '等待',
  running: '运行',
  success: '完成',
  failed: '失败',
  cancelling: '取消中',
  cancelled: '已取消',
}

export function StatusBadge({ status }: { status: TaskStatus }) {
  const isLive = isActiveTaskStatus(status)
  return (
    <span className={`status-badge status-${status}`}>
      {isLive && <span className="status-badge-dot" aria-hidden="true" />}
      {labels[status]}
    </span>
  )
}
