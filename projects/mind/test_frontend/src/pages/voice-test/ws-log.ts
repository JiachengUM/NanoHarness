export type VoiceLogLevel = 'info' | 'error'

export type VoiceLogItem = {
  id: number
  level: VoiceLogLevel
  text: string
}

type WsPayload = {
  type: string
  text?: string
  message?: string
  phase?: string
  wake_up_word?: string
  is_passed?: boolean
  reason?: string
  dataset_name?: string
  task_id?: string
  task_run_id?: string
  enable_judge?: boolean
  index?: number
  total?: number
  case_id?: string
  execution_success?: boolean
  execution_error?: string | null
  judge_status?: 'completed' | 'skipped' | 'failed' | 'not_run'
  judged?: number
  passed?: number | null
  pass_rate?: number | null
  batch_pace?: 'auto' | 'manual'
  case_ids?: string[]
  session_id?: string
  session_index?: number
  download_url?: string
  label?: string
  seconds?: number
  repeat_index?: number
  repeat_n?: number
}

function repeatSuffix(data: WsPayload): string {
  const repeatN = data.repeat_n || 0
  const repeatIndex = data.repeat_index || 0
  if (repeatN > 1 && repeatIndex > 0) {
    return ` 第${repeatIndex}/${repeatN}遍`
  }
  return ''
}

/** 仅写入可折叠「系统日志」区，对话/评测由 Case 时间线承载 */
export function formatSystemTrace(data: WsPayload): { level: VoiceLogLevel; text: string } | null {
  switch (data.type) {
    case 'ready':
      return { level: 'info', text: 'S2S 会话已就绪' }
    case 'ready_text':
      return { level: 'info', text: '文本 Agent 会话已就绪' }
    case 'log':
      return data.message ? { level: 'info', text: data.message } : null
    case 'countdown_wait':
      // 对话区气泡展示；系统日志已有同内容 log，此处不重复
      return null
    case 'listen_timeout':
      return data.message ? { level: 'error', text: data.message } : null
    case 'batch_started': {
      const pace = data.batch_pace === 'manual' ? '，手动' : ''
      const repeat =
        (data.repeat_n || 1) > 1 ? `，每条重复 ${data.repeat_n} 遍` : ''
      return {
        level: 'info',
        text: `开始批量测试：${data.dataset_name || ''}，共 ${data.total || 0} 条${pace}${repeat}${data.enable_judge ? '，启用自动评测' : '，不评测'}`,
      }
    }
    case 'batch_case_waiting': {
      const isFirst = (data.index || 0) === 1
      return {
        level: 'info',
        text: isFirst
          ? `[${data.index || 0}/${data.total || 0}] 等待播放：${data.case_id || ''}${repeatSuffix(data)}`
          : `[${data.index || 0}/${data.total || 0}] 上一条已完成，等待继续：${data.case_id || ''}${repeatSuffix(data)}`,
      }
    }
    case 'batch_case_started':
      return {
        level: 'info',
        text: `[${data.index || 0}/${data.total || 0}] 开始：${data.case_id || ''}${repeatSuffix(data)}`,
      }
    case 'batch_case_result': {
      if (data.execution_error === '已跳过') {
        return {
          level: 'info',
          text: `[${data.index || 0}/${data.total || 0}] ${data.case_id || ''}${repeatSuffix(data)}：已跳过`,
        }
      }
      const execution = data.execution_success ? '执行成功' : '执行失败'
      const judge =
        data.judge_status === 'completed'
          ? data.is_passed
            ? '，评测通过'
            : '，评测未通过'
          : data.judge_status === 'skipped'
            ? '，未评测'
            : data.judge_status === 'failed'
              ? '，评测失败'
              : ''
      return {
        level: data.execution_success ? 'info' : 'error',
        text: `[${data.index || 0}/${data.total || 0}] ${data.case_id || ''}${repeatSuffix(data)}：${execution}${judge}`,
      }
    }
    case 'task_run_created':
      return {
        level: 'info',
        text: `已创建测试记录：task_run_id=${data.task_run_id || ''}`,
      }
    case 'batch_done': {
      const judgeSummary = !data.enable_judge
        ? '未启用自动评测'
        : data.pass_rate == null
          ? '自动评测均未成功完成'
          : `评测 ${data.judged || 0} 条，通过 ${data.passed || 0} 条，通过率 ${(data.pass_rate * 100).toFixed(1)}%`
      return {
        level: 'info',
        text: `批量完成：执行成功 ${data.execution_success || 0}/${data.total || 0}；${judgeSummary}`,
      }
    }
    case 'error':
      return { level: 'error', text: data.message || '未知错误' }
    case 'done':
      return { level: 'info', text: '流程结束' }
    default:
      return null
  }
}
