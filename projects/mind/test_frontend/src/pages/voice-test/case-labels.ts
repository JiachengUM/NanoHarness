import type { CaseStatus } from './run-state'

export const caseStatusLabel: Record<CaseStatus, string> = {
  pending: '待播',
  waiting: '待播放',
  running: '播放中',
  done: '完成',
  skipped: '已跳过',
  failed: '失败',
}

export const caseStatusColor: Record<CaseStatus, string> = {
  pending: 'default',
  waiting: 'gold',
  running: 'processing',
  done: 'success',
  skipped: 'default',
  failed: 'error',
}
