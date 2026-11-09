import { formatSystemTrace, type VoiceLogItem, type VoiceLogLevel } from './ws-log'

export type CaseStatus = 'pending' | 'waiting' | 'running' | 'done' | 'skipped' | 'failed'

export type AgentReplyMode = 'listen' | 'scripted' | 'text'

export type DialogueTurn = {
  id: number
  fakePerson: string
  agentPartial: string
  agentFinal: string
  listening: boolean
  agentMode: AgentReplyMode
  sessionId?: string
}

export type CaseVerdict = {
  status: 'pending' | 'judging' | 'passed' | 'failed' | 'skipped'
  reason?: string
}

export type CaseBlock = {
  key: string
  index: number
  caseId: string
  total: number
  status: CaseStatus
  turns: DialogueTurn[]
  fullHistory?: string
  error?: string
  verdict?: CaseVerdict
  repeatIndex?: number
  repeatN?: number
}

export type SessionConnection = 'disconnected' | 'connecting' | 'connected' | 'ready' | 'error'

export type VoiceRunViewState = {
  connection: SessionConnection
  cases: CaseBlock[]
  activeCaseIndex: number | null
  systemTrace: VoiceLogItem[]
  traceIdSeq: number
  turnIdSeq: number
  goodbyeMarkers: string[]
  goodbyeReply: string
}

export const INITIAL_RUN_VIEW_STATE: VoiceRunViewState = {
  connection: 'disconnected',
  cases: [],
  activeCaseIndex: null,
  systemTrace: [],
  traceIdSeq: 0,
  turnIdSeq: 0,
  goodbyeMarkers: ['退下'],
  goodbyeReply: '（助手已结束会话）',
}

export type WsPayload = {
  type: string
  text?: string
  message?: string
  mode?: string
  phase?: string
  wake_up_word?: string
  is_passed?: boolean
  reason?: string
  dataset_name?: string
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
  execution_success_count?: number
  session_id?: string
  download_url?: string
  label?: string
  seconds?: number
  repeat_index?: number
  repeat_n?: number
  task_run_item_id?: string
}

export type RunAction =
  | { type: 'reset' }
  | { type: 'configure'; goodbyeMarkers: string[]; goodbyeReply: string }
  | { type: 'set_connection'; connection: SessionConnection }
  | { type: 'init_single_case'; caseId: string }
  | { type: 'push_system'; level: VoiceLogLevel; text: string }
  | { type: 'ws'; data: WsPayload }

export function countCaseSessions(caseBlock: CaseBlock): number {
  const ids: string[] = []
  for (const turn of caseBlock.turns) {
    if (turn.sessionId && !ids.includes(turn.sessionId)) {
      ids.push(turn.sessionId)
    }
  }
  return ids.length
}

export function isNewSessionTurn(turns: DialogueTurn[], turnIndex: number): boolean {
  if (turnIndex <= 0) {
    return false
  }
  const current = turns[turnIndex].sessionId
  const previous = turns[turnIndex - 1].sessionId
  return Boolean(current && previous && current !== previous)
}

export function sessionOrdinalAtTurn(turns: DialogueTurn[], turnIndex: number): number {
  let ordinal = 1
  for (let i = 1; i <= turnIndex; i += 1) {
    if (isNewSessionTurn(turns, i)) {
      ordinal += 1
    }
  }
  return ordinal
}

export function turnIndexInSession(turns: DialogueTurn[], turnIndex: number): number {
  let start = 0
  for (let i = 1; i <= turnIndex; i += 1) {
    if (isNewSessionTurn(turns, i)) {
      start = i
    }
  }
  return turnIndex - start + 1
}

function isGoodbyeQuery(text: string, markers: string[]): boolean {
  return markers.some((marker) => marker && text.includes(marker))
}

function pushTrace(state: VoiceRunViewState, level: VoiceLogLevel, text: string): VoiceRunViewState {
  const traceIdSeq = state.traceIdSeq + 1
  return {
    ...state,
    traceIdSeq,
    systemTrace: [...state.systemTrace, { id: traceIdSeq, level, text }],
  }
}

function nextTurnId(state: VoiceRunViewState): [number, VoiceRunViewState] {
  const turnIdSeq = state.turnIdSeq + 1
  return [turnIdSeq, { ...state, turnIdSeq }]
}

function updateCaseAt(
  state: VoiceRunViewState,
  index: number,
  patch: (caseBlock: CaseBlock) => CaseBlock,
): VoiceRunViewState {
  return {
    ...state,
    cases: state.cases.map((item) => (item.index === index ? patch(item) : item)),
  }
}

function getActiveIndex(state: VoiceRunViewState): number | null {
  if (state.activeCaseIndex !== null) {
    return state.activeCaseIndex
  }
  const running = state.cases.find((item) => item.status === 'running')
  if (running) {
    return running.index
  }
  const last = state.cases[state.cases.length - 1]
  return last?.index ?? null
}

function patchActiveTurn(
  state: VoiceRunViewState,
  patch: (turn: DialogueTurn) => DialogueTurn,
): VoiceRunViewState {
  const index = getActiveIndex(state)
  if (index === null) {
    return state
  }
  return updateCaseAt(state, index, (caseBlock) => {
    if (caseBlock.turns.length === 0) {
      return caseBlock
    }
    const turns = [...caseBlock.turns]
    turns[turns.length - 1] = patch(turns[turns.length - 1])
    return { ...caseBlock, turns }
  })
}

function handleDialogueEvent(state: VoiceRunViewState, data: WsPayload): VoiceRunViewState {
  switch (data.type) {
    case 'user_query': {
      const index = getActiveIndex(state)
      if (index === null) {
        return state
      }
      const [turnId, nextState] = nextTurnId(state)
      const spoken = data.text || ''
      const isTextMode = data.mode === 'text'
      const fakePerson = !isTextMode && data.wake_up_word ? `${data.wake_up_word}${spoken}` : spoken
      const goodbye = !isTextMode && isGoodbyeQuery(fakePerson, state.goodbyeMarkers)
      return updateCaseAt(nextState, index, (caseBlock) => ({
        ...caseBlock,
        turns: [
          ...caseBlock.turns,
          {
            id: turnId,
            fakePerson,
            agentPartial: '',
            agentFinal: goodbye ? state.goodbyeReply : '',
            listening: false,
            agentMode: goodbye ? 'scripted' : isTextMode ? 'text' : 'listen',
            sessionId: data.session_id,
          },
        ],
      }))
    }
    case 'config_reply':
      return patchActiveTurn(state, (turn) => ({
        ...turn,
        agentMode: 'scripted',
        agentFinal: data.text || state.goodbyeReply,
        agentPartial: '',
        listening: false,
      }))
    case 'asr_delta':
      return patchActiveTurn(state, (turn) => {
        if (turn.agentMode === 'scripted') {
          return turn
        }
        return {
          ...turn,
          agentPartial: data.text || '',
          listening: true,
        }
      })
    case 'asr_final':
      if (!data.text) {
        return state
      }
      return patchActiveTurn(state, (turn) => {
        if (turn.agentMode === 'scripted') {
          return turn
        }
        return {
          ...turn,
          agentFinal: data.text || '',
          agentPartial: '',
          listening: false,
          agentMode: turn.agentMode === 'text' ? 'text' : turn.agentMode,
        }
      })
    case 'listen_timeout':
      return patchActiveTurn(state, (turn) => {
        if (turn.agentMode === 'scripted') {
          return turn
        }
        return {
          ...turn,
          agentFinal: data.message || '等待外部回复超时',
          agentPartial: '',
          listening: false,
        }
      })
    case 'dialogue_history': {
      const index = getActiveIndex(state)
      if (index === null || !data.text) {
        return state
      }
      return updateCaseAt(state, index, (caseBlock) => ({
        ...caseBlock,
        fullHistory: data.text,
      }))
    }
    case 'judging': {
      const index = getActiveIndex(state)
      if (index === null) {
        return state
      }
      return updateCaseAt(state, index, (caseBlock) => ({
        ...caseBlock,
        verdict: { status: 'judging', reason: data.message },
      }))
    }
    case 'judge_result': {
      const index = getActiveIndex(state)
      if (index === null) {
        return state
      }
      return updateCaseAt(state, index, (caseBlock) => ({
        ...caseBlock,
        verdict: {
          status: data.is_passed ? 'passed' : 'failed',
          reason: data.reason,
        },
      }))
    }
    case 'judge_skipped': {
      const index = getActiveIndex(state)
      if (index === null) {
        return state
      }
      return updateCaseAt(state, index, (caseBlock) => ({
        ...caseBlock,
        verdict: {
          status: 'skipped',
          reason: data.message,
        },
      }))
    }
    case 'phase':
      if (data.phase === 'listening') {
        return patchActiveTurn(state, (turn) => {
          if (turn.agentMode === 'scripted') {
            return turn
          }
          return { ...turn, listening: true }
        })
      }
      if (data.phase === 'idle') {
        return patchActiveTurn(state, (turn) => {
          if (turn.agentMode === 'scripted') {
            return turn
          }
          return { ...turn, listening: false }
        })
      }
      return state
    case 'error': {
      const index = getActiveIndex(state)
      const message = data.message || '未知错误'
      if (index === null) {
        return state
      }
      return updateCaseAt(state, index, (caseBlock) => ({
        ...caseBlock,
        error: message,
      }))
    }
    default:
      return state
  }
}

function handleOrchestrationEvent(state: VoiceRunViewState, data: WsPayload): VoiceRunViewState {
  switch (data.type) {
    case 'ready':
      return { ...state, connection: 'ready' }
    case 'ready_text':
      return { ...state, connection: 'ready' }
    case 'batch_started': {
      const repeatN = Math.max(1, data.repeat_n || 1)
      const caseIds = data.case_ids || []
      const total = data.total || caseIds.length * repeatN
      const cases: CaseBlock[] = []
      let slot = 0
      // 外层轮次、内层 case：与后端 _run_voice_batch 顺序一致，slot 对齐
      for (let repeatIndex = 1; repeatIndex <= repeatN; repeatIndex += 1) {
        for (const caseId of caseIds) {
          slot += 1
          cases.push({
            key: `${slot}-${caseId}-r${repeatIndex}`,
            index: slot,
            caseId,
            total,
            status: 'pending' as CaseStatus,
            turns: [],
            repeatIndex: repeatN > 1 ? repeatIndex : undefined,
            repeatN: repeatN > 1 ? repeatN : undefined,
          })
        }
      }
      return { ...state, cases }
    }
    case 'batch_case_waiting':
      if (!data.index) {
        return state
      }
      return {
        ...updateCaseAt(state, data.index, (caseBlock) => ({ ...caseBlock, status: 'waiting' })),
        activeCaseIndex: data.index,
      }
    case 'batch_case_started':
      if (!data.index) {
        return state
      }
      return {
        ...updateCaseAt(state, data.index, (caseBlock) => ({
          ...caseBlock,
          caseId: data.case_id || caseBlock.caseId,
          total: data.total || caseBlock.total,
          status: 'running',
          turns: [],
          fullHistory: undefined,
          error: undefined,
          verdict: undefined,
          repeatIndex: data.repeat_index ?? caseBlock.repeatIndex,
          repeatN: data.repeat_n ?? caseBlock.repeatN,
        })),
        activeCaseIndex: data.index,
      }
    case 'batch_case_result': {
      if (!data.index) {
        return state
      }
      const resultStatus: CaseStatus =
        data.execution_error === '已跳过'
          ? 'skipped'
          : data.execution_success
            ? 'done'
            : 'failed'
      let next = updateCaseAt(state, data.index, (caseBlock) => ({
        ...caseBlock,
        status: resultStatus,
        error: data.execution_success ? caseBlock.error : data.execution_error || caseBlock.error,
      }))
      if (
        data.judge_status === 'completed' &&
        data.is_passed !== undefined &&
        data.is_passed !== null
      ) {
        next = updateCaseAt(next, data.index, (caseBlock) => ({
          ...caseBlock,
          verdict: {
            status: data.is_passed ? 'passed' : 'failed',
            reason: data.reason || caseBlock.verdict?.reason,
          },
        }))
      }
      return next
    }
    case 'batch_paused':
      return state
    case 'batch_resumed':
      return state
    case 'done':
      return {
        ...state,
        connection: state.connection === 'error' ? 'error' : 'connected',
        cases: state.cases.map((item) => {
          if (item.status !== 'running') {
            return item
          }
          return {
            ...item,
            status: item.error ? 'failed' : 'done',
          }
        }),
      }
    default:
      return state
  }
}

export function shouldShowAgentBubble(turn: DialogueTurn): boolean {
  if (turn.agentMode === 'scripted') {
    return Boolean(turn.agentFinal)
  }
  if (turn.agentMode === 'text') {
    return true
  }
  if (turn.agentFinal || turn.agentPartial) {
    return true
  }
  return turn.listening
}

export function agentBubbleText(turn: DialogueTurn): string {
  if (turn.agentFinal) {
    return turn.agentFinal
  }
  if (turn.agentPartial) {
    return turn.agentPartial
  }
  if (turn.agentMode === 'text') {
    return '思考中…'
  }
  if (turn.listening) {
    return '识别中…'
  }
  return ''
}

export function voiceRunReducer(state: VoiceRunViewState, action: RunAction): VoiceRunViewState {
  switch (action.type) {
    case 'reset':
      return { ...INITIAL_RUN_VIEW_STATE }
    case 'configure':
      return {
        ...state,
        goodbyeMarkers: action.goodbyeMarkers,
        goodbyeReply: action.goodbyeReply,
      }
    case 'set_connection':
      return { ...state, connection: action.connection }
    case 'init_single_case':
      return {
        ...state,
        cases: [
          {
            key: `1-${action.caseId}`,
            index: 1,
            caseId: action.caseId,
            total: 1,
            status: 'running',
            turns: [],
          },
        ],
        activeCaseIndex: 1,
      }
    case 'push_system':
      return pushTrace(state, action.level, action.text)
    case 'ws': {
      let next = handleDialogueEvent(state, action.data)
      next = handleOrchestrationEvent(next, action.data)
      const traceLine = formatSystemTrace(action.data)
      if (traceLine) {
        next = pushTrace(next, traceLine.level, traceLine.text)
      }
      return next
    }
    default:
      return state
  }
}
