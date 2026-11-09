/**
 * RunConsole：运行控制面板（左栏）。
 * 连接状态、case 列表、被测助手选择、运行/停止、运行摘要。
 */
import { useState } from 'react'
import type { CaseSummary } from '../adapters/visualizerClient'
import type { ConnectionState } from '../adapters/visualizerClient'
import type { ConsoleState } from '../app/consoleReducer'
import { formatDuration } from '../app/projections'

export type AssistantKind = 'mock' | 'v2' | 'adapter_v2' | 'v2_adapter'

const ASSISTANT_OPTIONS: Array<{ kind: AssistantKind; label: string; hint: string }> = [
  {
    kind: 'mock',
    label: 'Mock',
    hint: '规则助手瞬回短句：验证链路/快进/状态检查，看不到插话重叠与主动提醒',
  },
  {
    kind: 'adapter_v2',
    label: 'adapter_v2',
    hint: '新协议（事件源适配器）：MockAdapter 演示多源汇合/异步工具回灌/插话打断/主动提醒',
  },
  {
    kind: 'v2_adapter',
    label: 'v2 Agent（新协议）',
    hint: '真实 LLM 经 V2AgentAdapter 接入：真实对话、异步工具回灌、插话打断、主动提醒完整可见',
  },
  {
    kind: 'v2',
    label: 'v2 Agent',
    hint: '真实 LLM（需 API）：思考数秒后开口、流式回复，插话重叠/定时提醒/主动智能完整可见',
  },
]

export interface RunConsoleProps {
  state: ConsoleState
  onSelect(caseId: string): void
  onStart(caseId: string, assistantKind: AssistantKind): void
  onStop(): void
}

const RUN_STATUS_LABEL: Record<ConsoleState['run']['status'], string> = {
  idle: '空闲',
  running: '运行中',
  finished: '已完成',
  cancelled: '已停止',
  error: '出错',
}

export function connectionLabel(connection: ConnectionState): string {
  switch (connection) {
    case 'open':
      return '已连接'
    case 'connecting':
      return '连接中'
    default:
      return '未连接'
  }
}

export function RunConsole({ state, onSelect, onStart, onStop }: RunConsoleProps) {
  const { connection, cases, selectedCaseId, run } = state
  const running = run.status === 'running'
  const [assistantKind, setAssistantKind] = useState<AssistantKind>('mock')
  const activeHint = ASSISTANT_OPTIONS.find((o) => o.kind === assistantKind)?.hint ?? ''

  return (
    <aside className="run-console">
      <header className="panel-header">
        <h2>运行控制</h2>
        <span className={`connection-badge connection-${connection}`}>
          {connectionLabel(connection)}
        </span>
      </header>

      <section className="run-case-list" aria-label="case 列表">
        {cases.length === 0 && connection === 'open' && (
          <p className="empty-hint">（无可用 case）</p>
        )}
        {cases.map((item: CaseSummary) => (
          <button
            key={item.id}
            type="button"
            className={[
              'case-item',
              item.id === selectedCaseId ? 'case-selected' : '',
            ]
              .filter(Boolean)
              .join(' ')}
            disabled={running}
            aria-pressed={item.id === selectedCaseId}
            onClick={() => onSelect(item.id)}
            title={item.caseDescription}
          >
            <span className="case-item-name">{item.caseName || item.id}</span>
            <span className="case-item-id">{item.id}</span>
          </button>
        ))}
      </section>

      <section className="run-controls" aria-label="运行控制">
        <div className="run-status-row">
          <span className={`run-status run-status-${run.status}`}>
            {RUN_STATUS_LABEL[run.status]}
          </span>
          {run.caseName && <span className="run-case-name">{run.caseName}</span>}
        </div>
        <div className="assistant-picker" role="radiogroup" aria-label="被测助手">
          <span className="assistant-picker-label">被测助手</span>
          <div className="assistant-options">
            {ASSISTANT_OPTIONS.map((option) => (
              <button
                key={option.kind}
                type="button"
                role="radio"
                aria-checked={assistantKind === option.kind}
                className={[
                  'assistant-option',
                  assistantKind === option.kind ? 'assistant-option-active' : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
                disabled={running}
                onClick={() => setAssistantKind(option.kind)}
              >
                {option.label}
              </button>
            ))}
          </div>
          <p className="assistant-hint">{activeHint}</p>
        </div>
        {running ? (
          <button
            type="button"
            className="primary-button stop-button"
            onClick={onStop}
          >
            停止运行
          </button>
        ) : (
          <button
            type="button"
            className="primary-button"
            disabled={!selectedCaseId || connection !== 'open'}
            onClick={() => onStart(selectedCaseId, assistantKind)}
          >
            运行选中 case
          </button>
        )}
        {run.errorMessage && (
          <p className="run-error-message" role="alert">
            {run.errorMessage}
          </p>
        )}
      </section>

      {run.summary && (
        <section className="run-summary" aria-label="运行摘要">
          <h3>运行摘要</h3>
          <dl>
            <div>
              <dt>总耗时</dt>
              <dd>{formatDuration(run.summary.durationSeconds * 1000)}</dd>
            </div>
            <div>
              <dt>话语数</dt>
              <dd>{run.summary.totalUtterances}</dd>
            </div>
            <div>
              <dt>状态检查</dt>
              <dd>
                <span className={run.summary.stateCheckPassed ? 'ok-text' : 'fail-text'}>
                  {run.summary.stateChecksPassed} 通过 /{' '}
                  {run.summary.stateChecksFailed} 失败
                </span>
              </dd>
            </div>
          </dl>
        </section>
      )}

    </aside>
  )
}
