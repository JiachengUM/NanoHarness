import { describe, expect, it } from 'vitest'
import {
  isFakePersonRole,
  normalizeEvent,
  speakerLabel,
  type EventEnvelope,
} from './events'

function envelope(
  kind: string,
  payload: Record<string, unknown>,
  seq = 1,
): EventEnvelope {
  return {
    seq,
    wall_time: '2026-08-26T10:00:00',
    mock_time: '2026-08-26T10:00:05',
    kind,
    payload,
  }
}

describe('normalizeEvent', () => {
  it('归一化 case_started', () => {
    const event = normalizeEvent(
      envelope('case_started', {
        case_id: 'builtin-simple-ac',
        case_name: '内置_开空调',
        case_description: '描述',
        t0: '2026-08-26T10:00:00',
        session_id: 'sess-1',
      }),
    )
    expect(event).toMatchObject({
      type: 'case_started',
      seq: 1,
      mockTime: '2026-08-26T10:00:05',
      caseId: 'builtin-simple-ac',
      caseName: '内置_开空调',
    })
  })

  it('归一化 case_started 的 initial_car_info 与 car_state_groups', () => {
    const event = normalizeEvent(
      envelope('case_started', {
        case_id: 'c1',
        case_name: 'n',
        case_description: '',
        t0: '2026-08-26T10:00:00',
        session_id: 's',
        initial_car_info: { 空调开启状态及模式: '关闭中', 多媒体播放状态: '停止中' },
        car_state_groups: {
          空调: ['空调开启状态及模式'],
          媒体: ['多媒体播放状态'],
        },
      }),
    )
    if (event.type !== 'case_started') {
      throw new Error(`期望 case_started，实际 ${event.type}`)
    }
    expect(event.initialCarInfo).toEqual({
      空调开启状态及模式: '关闭中',
      多媒体播放状态: '停止中',
    })
    expect(event.carStateGroups).toEqual({
      空调: ['空调开启状态及模式'],
      媒体: ['多媒体播放状态'],
    })
  })

  it('car_state_groups 缺失或非法时归一化为 null（旧事件流兼容）', () => {
    const missing = normalizeEvent(
      envelope('case_started', {
        case_id: 'c1',
        case_name: 'n',
        case_description: '',
        t0: '2026-08-26T10:00:00',
        session_id: 's',
      }),
    )
    if (missing.type !== 'case_started') throw new Error('期望 case_started')
    expect(missing.carStateGroups).toBeNull()

    const invalid = normalizeEvent(
      envelope('case_started', {
        case_id: 'c1',
        case_name: 'n',
        case_description: '',
        t0: '2026-08-26T10:00:00',
        session_id: 's',
        car_state_groups: { 空调: 'not-an-array' },
      }),
    )
    if (invalid.type !== 'case_started') throw new Error('期望 case_started')
    expect(invalid.carStateGroups).toBeNull()
  })

  it('归一化 utterance（含打断成因与 segments）', () => {
    const event = normalizeEvent(
      envelope('utterance', {
        speaker_kind: 'assistant_reply',
        role: 'assistant',
        content: '好的，已',
        started_at: '2026-08-26T10:00:06',
        ended_at: '2026-08-26T10:00:08',
        is_partial: true,
        interrupted_by_barge_in: true,
        speech_duration: 2.0,
        ttft: 3.1,
        is_proactive: false,
        segments: [['2026-08-26T10:00:06', '好的，'], ['2026-08-26T10:00:07', '已']],
      }),
    )
    if (event.type !== 'utterance') {
      throw new Error(`期望 utterance，实际 ${event.type}`)
    }
    expect(event.isPartial).toBe(true)
    expect(event.interruptedByBargeIn).toBe(true)
    expect(event.segments).toHaveLength(2)
    expect(event.segments[0]).toEqual(['2026-08-26T10:00:06', '好的，'])
  })

  it('归一化 acceleration（from/to 保留 iso）', () => {
    const event = normalizeEvent(
      envelope('acceleration', {
        from: '2026-08-26T10:00:10',
        to: '2026-08-27T10:00:10',
      }),
    )
    if (event.type !== 'acceleration') {
      throw new Error(`期望 acceleration，实际 ${event.type}`)
    }
    expect(event.from).toBe('2026-08-26T10:00:10')
    expect(event.to).toBe('2026-08-27T10:00:10')
  })

  it('归一化 tool_call / tool_result（含 task_id；旧事件流无 task_id → null）', () => {
    const call = normalizeEvent(
      envelope('tool_call', {
        tool_name: 'poi_search',
        tool_args: { q: '上海博物馆' },
        task_id: 't-1',
      }),
    )
    if (call.type !== 'tool_call') throw new Error('期望 tool_call')
    expect(call.taskId).toBe('t-1')

    const result = normalizeEvent(
      envelope('tool_result', {
        tool_name: 'poi_search',
        result: '结果',
        duration_ms: 3200,
        task_id: 't-1',
      }),
    )
    if (result.type !== 'tool_result') throw new Error('期望 tool_result')
    expect(result.taskId).toBe('t-1')
    expect(result.durationMs).toBe(3200)

    // 旧事件流 / 同步路径无 task_id → null（前端回退 toolName FIFO 配对）
    const legacy = normalizeEvent(
      envelope('tool_call', { tool_name: 'poi_search', tool_args: {} }),
    )
    if (legacy.type !== 'tool_call') throw new Error('期望 tool_call')
    expect(legacy.taskId).toBeNull()
  })

  it('归一化 judge_verdict（snake→camel，含打分明细与断言列表）', () => {
    const event = normalizeEvent(
      envelope('judge_verdict', {
        case_id: 'builtin-simple-ac',
        overall_passed: true,
        score: 100.0,
        score_breakdown: {
          must_pass_total: 2,
          must_pass_passed: 2,
          bonus_total: 1,
          bonus_passed: 0,
          state_check_total: 1,
          state_check_passed: 1,
          score: 80.0,
          passed: true,
        },
        assertion_results: [
          {
            assertion: '空调被打开',
            assertion_type: 'must_pass',
            passed: true,
            reasoning: '轨迹显示空调已开启',
            evidence: ['car_set_state 空调=制冷中', '助手回复"好的"'],
          },
          {
            assertion: '口头确认温度',
            assertion_type: 'bonus',
            passed: false,
            reasoning: '助手未口头播报温度',
            evidence: [],
          },
        ],
        summary: '必过全过，加分未过',
        judged_at: '2026-08-27T10:00:00',
      }),
    )
    if (event.type !== 'judge_verdict') {
      throw new Error(`期望 judge_verdict，实际 ${event.type}`)
    }
    expect(event.error).toBeNull()
    expect(event.verdict?.caseId).toBe('builtin-simple-ac')
    expect(event.verdict?.overallPassed).toBe(true)
    expect(event.verdict?.score).toBe(100)
    expect(event.verdict?.scoreBreakdown?.mustPassTotal).toBe(2)
    expect(event.verdict?.scoreBreakdown?.bonusPassed).toBe(0)
    expect(event.verdict?.scoreBreakdown?.passed).toBe(true)
    expect(event.verdict?.assertionResults).toHaveLength(2)
    expect(event.verdict?.assertionResults[0]).toMatchObject({
      assertionType: 'must_pass',
      passed: true,
      evidence: ['car_set_state 空调=制冷中', '助手回复"好的"'],
    })
    expect(event.verdict?.assertionResults[1].assertionType).toBe('bonus')
    expect(event.verdict?.summary).toBe('必过全过，加分未过')
  })

  it('judge_verdict 失败 payload → verdict 为 null 且带 error 文本', () => {
    const event = normalizeEvent(
      envelope('judge_verdict', { error: "RuntimeError('LLM down')" }),
    )
    if (event.type !== 'judge_verdict') {
      throw new Error(`期望 judge_verdict，实际 ${event.type}`)
    }
    expect(event.verdict).toBeNull()
    expect(event.error).toBe("RuntimeError('LLM down')")
  })

  it('未知 kind 归一化为 unknown_event（中立保留 payload）', () => {
    const event = normalizeEvent(
      envelope('future_new_event', { anything: 42, nested: { a: 1 } }),
    )
    if (event.type !== 'unknown_event') {
      throw new Error(`期望 unknown_event，实际 ${event.type}`)
    }
    expect(event.kind).toBe('future_new_event')
    expect(event.payload).toEqual({ anything: 42, nested: { a: 1 } })
  })

  it('字段缺失时给默认值（宽松解析不抛错）', () => {
    const event = normalizeEvent(envelope('utterance', {}))
    if (event.type !== 'utterance') {
      throw new Error(`期望 utterance，实际 ${event.type}`)
    }
    expect(event.content).toBe('')
    expect(event.isPartial).toBe(false)
    expect(event.segments).toEqual([])
  })
})

describe('speaker 工具', () => {
  it('isFakePersonRole 区分假人与助手', () => {
    expect(isFakePersonRole('fake_person:driver')).toBe(true)
    expect(isFakePersonRole('assistant')).toBe(false)
  })

  it('speakerLabel 提取人设名', () => {
    expect(speakerLabel('fake_person:driver')).toBe('假人·driver')
    expect(speakerLabel('assistant')).toBe('助手')
  })
})
