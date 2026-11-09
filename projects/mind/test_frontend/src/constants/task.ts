export const TASK_RUN_STATUS = {
  PENDING: 'pending',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
}

export const TASK_RUN_STATUS_OPTIONS = [
  {
    label: '待运行',
    value: TASK_RUN_STATUS.PENDING,
  },
  {
    label: '运行中',
    value: TASK_RUN_STATUS.RUNNING,
  },
  {
    label: '已完成',
    value: TASK_RUN_STATUS.COMPLETED,
  },
  {
    label: '已失败',
    value: TASK_RUN_STATUS.FAILED,
  },
]

export const TASK_RUN_ITEM_STATUS = {
  PENDING: 'pending',
  RUNNING: 'running',
  SKIPPED: 'skipped',
  EVALUATING: 'evaluating',
  COMPLETED: 'completed',
  FAILED: 'failed',
}

export const TASK_RUN_ITEM_STATUS_OPTIONS = [
  {
    label: '待运行',
    value: TASK_RUN_ITEM_STATUS.PENDING,
  },
  {
    label: '运行中',
    value: TASK_RUN_ITEM_STATUS.RUNNING,
  },
  {
    label: '已跳过',
    value: TASK_RUN_ITEM_STATUS.SKIPPED,
  },
  {
    label: '评估中',
    value: TASK_RUN_ITEM_STATUS.EVALUATING,
  },
  {
    label: '已完成',
    value: TASK_RUN_ITEM_STATUS.COMPLETED,
  },
  {
    label: '已失败',
    value: TASK_RUN_ITEM_STATUS.FAILED,
  },
]

export const IS_PASS = {
  TRUE: true,
  FALSE: false,
}

export const IS_PASS_OPTIONS = [
  {
    label: '通过',
    value: String(IS_PASS.TRUE),
  },
  {
    label: '未通过',
    value: String(IS_PASS.FALSE),
  },
]
