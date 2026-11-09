/**
 * VerdictPanel：裁判终局评判面板（右栏下方）。
 *
 * case 自然完成后服务器自动发起终局评判（Judge LLM），结果以
 * judge_verdict 事件到达；也可手动点「重新评判」再跑一次。
 * 展示总分 / 及格判定 / 打分明细 / 每条断言的通过情况与裁判理由。
 */
import type { JudgeState, RunState } from '../app/consoleReducer'
import type {
  AssertionResultView,
  JudgeVerdictData,
  ScoreBreakdownView,
} from '../domain/events'

export interface VerdictPanelProps {
  run: RunState
  judge: JudgeState
  onJudge: () => void
}

function formatScore(score: number): string {
  return Number.isInteger(score) ? `${score}` : score.toFixed(1)
}

function BreakdownRow({ label, passed, total }: { label: string; passed: number; total: number }) {
  return (
    <span className="verdict-breakdown-item">
      {label}
      <b className={passed === total ? 'tone-ok-text' : 'tone-fail-text'}>
        {passed}/{total}
      </b>
    </span>
  )
}

function BreakdownView({ breakdown }: { breakdown: ScoreBreakdownView }) {
  return (
    <div className="verdict-breakdown">
      <BreakdownRow
        label="必过"
        passed={breakdown.mustPassPassed}
        total={breakdown.mustPassTotal}
      />
      <BreakdownRow
        label="加分"
        passed={breakdown.bonusPassed}
        total={breakdown.bonusTotal}
      />
      {breakdown.stateCheckTotal > 0 && (
        <BreakdownRow
          label="状态检查"
          passed={breakdown.stateCheckPassed}
          total={breakdown.stateCheckTotal}
        />
      )}
    </div>
  )
}

function AssertionItem({ result }: { result: AssertionResultView }) {
  return (
    <li
      className={`verdict-assertion ${result.passed ? 'assertion-passed' : 'assertion-failed'}`}
    >
      <header>
        <span className="assertion-mark" aria-hidden>
          {result.passed ? '✓' : '✗'}
        </span>
        <span className="assertion-text">{result.assertion}</span>
        <span className={`assertion-type type-${result.assertionType}`}>
          {result.assertionType === 'must_pass' ? '必过' : '加分'}
        </span>
      </header>
      {result.reasoning !== '' && (
        <p className="assertion-reasoning">{result.reasoning}</p>
      )}
      {result.evidence.length > 0 && (
        <ul className="assertion-evidence">
          {result.evidence.map((item, index) => (
            <li key={index}>证据：{item}</li>
          ))}
        </ul>
      )}
    </li>
  )
}

function VerdictBody({ verdict }: { verdict: JudgeVerdictData }) {
  const passed = verdict.overallPassed
  return (
    <>
      <div className={`verdict-score ${passed ? 'verdict-pass' : 'verdict-fail'}`}>
        <span className="verdict-score-number">{formatScore(verdict.score)}</span>
        <span className="verdict-score-badge">
          {passed ? '及格' : '不及格'}
        </span>
      </div>
      {verdict.scoreBreakdown && <BreakdownView breakdown={verdict.scoreBreakdown} />}
      {verdict.summary !== '' && (
        <p className="verdict-summary">{verdict.summary}</p>
      )}
      {verdict.assertionResults.length > 0 && (
        <ul className="verdict-assertions">
          {verdict.assertionResults.map((result, index) => (
            <AssertionItem key={index} result={result} />
          ))}
        </ul>
      )}
    </>
  )
}

export function VerdictPanel({ run, judge, onJudge }: VerdictPanelProps) {
  const canJudge = run.status === 'finished' || run.status === 'cancelled'
  return (
    <section className="verdict-panel" aria-label="裁判评判">
      <header className="panel-header">
        <h2>裁判评判</h2>
        {canJudge && judge.status !== 'pending' && (
          <button
            type="button"
            className="judge-button"
            onClick={onJudge}
          >
            {judge.status === 'done' || judge.status === 'error' ? '重新评判' : '开始评判'}
          </button>
        )}
      </header>

      <div className="verdict-body">
        {judge.status === 'idle' && (
          <p className="empty-hint">
            {canJudge
              ? '运行完成，裁判将自动开始终局评判。'
              : '运行 case 后裁判将自动发起终局评判。'}
          </p>
        )}
        {judge.status === 'pending' && (
          <p className="verdict-pending">裁判正在自动评判（LLM 分析完整轨迹，需数秒）…</p>
        )}
        {judge.status === 'error' && (
          <p className="verdict-error">{judge.errorMessage}</p>
        )}
        {judge.status === 'done' && judge.verdict && (
          <VerdictBody verdict={judge.verdict} />
        )}
      </div>
    </section>
  )
}
