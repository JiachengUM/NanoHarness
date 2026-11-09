import { describe, expect, it } from 'vitest'
import { consoleReducer, initialConsoleState } from './consoleReducer'
import { initialPlannerState } from './planDagReducer'

const timestamp = '2026-06-16T10:00:00.000Z'

describe('console reducer', () => {
  it('retains runtime relationship history across conversation turns and reset clears it', () => {
    const t0 = '2026-07-13T10:00:00.000Z'
    const t1 = '2026-07-13T10:00:01.000Z'
    const t2 = '2026-07-13T10:00:02.000Z'

    let state = consoleReducer(initialConsoleState(), {
      type: 'startConversation',
      input: '第一轮',
      userMessageId: 'user-1',
      assistantMessageId: 'agent-1',
      timestamp: t0,
    })

    expect(state.runtimeTrace.entries).toMatchObject([{
      kind: 'user.submitted',
      label: '第一轮',
      messageId: 'agent-1',
      timestamp: t0,
    }])
    expect(state.runtimeTrace.entries[0].timestamp).toBe(state.messages[0].createdAt)
    expect(state.acceptedPlaybackMessageId).toBe('agent-1')
    expect(state.acceptedPlaybackRevision).toBe(1)

    state = consoleReducer(state, {
      type: 'event',
      event: {
        id: 'created-1',
        type: 'task.created',
        timestamp: t1,
        taskId: 'task-1',
        toolName: 'tool',
        title: '委派任务',
        arguments: {},
        originMessageId: 'agent-1',
      },
    })

    expect(state.runtimeTrace.entries.slice(-2)).toMatchObject([
      {
        id: 'agent-delegated:agent-1',
        kind: 'agent.delegated',
        messageId: 'agent-1',
        timestamp: t1,
        endTimestamp: t1,
      },
      {
        id: 'created-1',
        kind: 'task.delegated',
        taskId: 'task-1',
        originMessageId: 'agent-1',
        timestamp: t1,
      },
    ])

    state = consoleReducer(state, {
      type: 'startConversation',
      input: '第二轮',
      userMessageId: 'user-2',
      assistantMessageId: 'agent-2',
      timestamp: t2,
    })

    expect(state.runtimeTrace.entries.map((entry) => entry.kind)).toEqual([
      'user.submitted',
      'agent.delegated',
      'task.delegated',
      'user.submitted',
    ])
    expect(state.runtimeTrace.entries.at(-1)).toMatchObject({
      label: '第二轮',
      messageId: 'agent-2',
      timestamp: t2,
    })
    expect(state.acceptedPlaybackMessageId).toBe('agent-2')
    expect(state.acceptedPlaybackRevision).toBe(2)

    state = consoleReducer(state, { type: 'reset' })
    expect(state.runtimeTrace.entries).toEqual([])
  })

  it('keeps conversation state across follow-up turns', () => {
    let state = consoleReducer(initialConsoleState(), {
      type: 'startConversation',
      input: 'first request',
      userMessageId: 'user-1',
      assistantMessageId: 'agent-1',
      timestamp: '2026-06-16T10:00:00.000Z',
    })

    state = consoleReducer(state, {
      type: 'startConversation',
      input: 'follow up',
      userMessageId: 'user-2',
      assistantMessageId: 'agent-2',
      timestamp: '2026-06-16T10:00:05.000Z',
    })

    expect(state.messages).toMatchObject([
      {
        id: 'user-1',
        role: 'user',
        content: 'first request',
        status: 'complete',
        createdAt: '2026-06-16T10:00:00.000Z',
      },
      {
        id: 'agent-1',
        messageId: 'agent-1',
        role: 'assistant',
        status: 'interrupted',
        createdAt: '2026-06-16T10:00:00.000Z',
      },
      {
        id: 'user-2',
        role: 'user',
        content: 'follow up',
        status: 'complete',
        createdAt: '2026-06-16T10:00:05.000Z',
      },
      {
        id: 'agent-2',
        messageId: 'agent-2',
        role: 'assistant',
        status: 'streaming',
        createdAt: '2026-06-16T10:00:05.000Z',
      },
    ])
    expect(state.activeAssistantMessageId).toBe('agent-2')
    expect(state.isPlaying).toBe(true)
  })

  it('ignores late deltas for interrupted assistant streams', () => {
    let state = consoleReducer(initialConsoleState(), {
      type: 'startConversation',
      input: 'first request',
      userMessageId: 'user-1',
      assistantMessageId: 'agent-1',
      timestamp: '2026-06-16T10:00:00.000Z',
    })

    state = consoleReducer(state, {
      type: 'event',
      event: {
        id: 'delta-1',
        type: 'agent.text.delta',
        messageId: 'agent-1',
        delta: '旧回复前半段',
        timestamp: '2026-06-16T10:00:02.000Z',
      },
    })

    state = consoleReducer(state, {
      type: 'startConversation',
      input: 'interrupting request',
      userMessageId: 'user-2',
      assistantMessageId: 'agent-2',
      timestamp: '2026-06-16T10:00:03.000Z',
    })

    state = consoleReducer(state, {
      type: 'event',
      event: {
        id: 'late-delta-1',
        type: 'agent.text.delta',
        messageId: 'agent-1',
        delta: '迟到旧回复',
        timestamp: '2026-06-16T10:00:04.000Z',
      },
    })

    expect(state.messages).toMatchObject([
      { id: 'user-1', role: 'user', content: 'first request', status: 'complete' },
      { id: 'agent-1', role: 'assistant', content: '旧回复前半段', status: 'interrupted' },
      { id: 'user-2', role: 'user', content: 'interrupting request', status: 'complete' },
      { id: 'agent-2', role: 'assistant', content: '', status: 'streaming' },
    ])
    expect(state.messages).toHaveLength(4)
  })

  it('ignores stale foreground agent events in both message and runtime projections', () => {
    let state = consoleReducer(initialConsoleState(), {
      type: 'startConversation',
      input: 'first request',
      userMessageId: 'user-1',
      assistantMessageId: 'agent-1',
      timestamp: '2026-07-13T10:00:00.000Z',
    })
    state = consoleReducer(state, {
      type: 'startConversation',
      input: 'second request',
      userMessageId: 'user-2',
      assistantMessageId: 'agent-2',
      timestamp: '2026-07-13T10:00:01.000Z',
    })

    const messagesBeforeLateEvents = state.messages
    const runtimeTraceBeforeLateEvents = state.runtimeTrace

    state = consoleReducer(state, {
      type: 'event',
      event: {
        id: 'late-delta-1',
        type: 'agent.text.delta',
        messageId: 'agent-1',
        delta: '迟到旧回复',
        timestamp: '2026-07-13T10:00:02.000Z',
      },
    })
    state = consoleReducer(state, {
      type: 'event',
      event: {
        id: 'late-done-1',
        type: 'agent.text.done',
        messageId: 'agent-1',
        timestamp: '2026-07-13T10:00:03.000Z',
      },
    })

    expect(state.messages).toBe(messagesBeforeLateEvents)
    expect(state.runtimeTrace).toBe(runtimeTraceBeforeLateEvents)
    expect(state.runtimeTrace.entries.map((entry) => entry.kind)).toEqual([
      'user.submitted',
      'user.submitted',
    ])
  })

  it('keeps a background task result and its trace active across a newer turn', () => {
    const t0 = '2026-07-13T10:00:00.000Z'
    const t1 = '2026-07-13T10:00:01.000Z'
    const t2 = '2026-07-13T10:00:02.000Z'
    const t3 = '2026-07-13T10:00:03.000Z'
    const t4 = '2026-07-13T10:00:04.000Z'
    const t5 = '2026-07-13T10:00:05.000Z'

    let state = consoleReducer(initialConsoleState(), {
      type: 'startConversation',
      input: '找徐汇滨江3公里内、停车方便的餐厅',
      userMessageId: 'user-origin',
      assistantMessageId: 'agent-origin',
      timestamp: t0,
    })
    state = consoleReducer(state, {
      type: 'event',
      event: {
        id: 'task-created',
        type: 'task.created',
        timestamp: t1,
        taskId: 'poi-1',
        toolName: '地点搜索工具',
        title: '地点搜索工具',
        arguments: {},
        originMessageId: 'agent-origin',
      },
    })
    state = consoleReducer(state, {
      type: 'event',
      event: {
        id: 'result-start',
        type: 'agent.text.start',
        timestamp: t2,
        messageId: 'task-result-poi-1',
        originMessageId: 'agent-origin',
        sourceTaskId: 'poi-1',
      },
    })
    state = consoleReducer(state, {
      type: 'startConversation',
      input: '顺便说说今天的天气',
      userMessageId: 'user-current',
      assistantMessageId: 'agent-current',
      timestamp: t3,
    })

    for (const event of [
      {
        id: 'result-delta',
        type: 'agent.text.delta' as const,
        timestamp: t4,
        messageId: 'task-result-poi-1',
        originMessageId: 'agent-origin',
        sourceTaskId: 'poi-1',
        delta: '找到 3 家候选餐厅。',
      },
      {
        id: 'result-done',
        type: 'agent.text.done' as const,
        timestamp: t5,
        messageId: 'task-result-poi-1',
        originMessageId: 'agent-origin',
        sourceTaskId: 'poi-1',
      },
    ]) {
      state = consoleReducer(state, { type: 'event', event })
    }

    expect(state.messages.find(
      (message) => message.sourceTaskId === 'poi-1',
    )).toMatchObject({
      id: 'task-result-poi-1',
      messageId: 'task-result-poi-1',
      sourceTaskId: 'poi-1',
      sourceTaskTitle: '地点搜索工具',
      content: '找到 3 家候选餐厅。',
      status: 'complete',
    })
    expect(state.runtimeTrace.entries.find(
      (entry) => entry.id === 'result-start',
    )).toMatchObject({
      sourceTaskId: 'poi-1',
      status: 'complete',
      endTimestamp: t5,
      terminalEventId: 'result-done',
    })
    expect(state.activeAssistantMessageId).toBe('agent-current')
    expect(state.isPlaying).toBe(true)
  })

  it('creates separate bubbles for parallel task results', () => {
    let state = consoleReducer(initialConsoleState(), {
      type: 'startConversation',
      input: '同时搜索餐厅和停车场',
      userMessageId: 'user-origin',
      assistantMessageId: 'agent-origin',
      timestamp,
    })

    for (const [taskId, title] of [['poi-1', '地点搜索工具'], ['parking-1', '停车场搜索工具']] as const) {
      state = consoleReducer(state, {
        type: 'event',
        event: {
          id: `created-${taskId}`,
          type: 'task.created',
          timestamp,
          taskId,
          toolName: title,
          title,
          arguments: {},
          originMessageId: 'agent-origin',
        },
      })
      state = consoleReducer(state, {
        type: 'event',
        event: {
          id: `delta-${taskId}`,
          type: 'agent.text.delta',
          timestamp,
          messageId: `task-result-${taskId}`,
          originMessageId: 'agent-origin',
          sourceTaskId: taskId,
          delta: `${title}结果`,
        },
      })
    }

    expect(state.messages.filter((message) => message.sourceTaskId)).toMatchObject([
      { sourceTaskId: 'poi-1', content: '地点搜索工具结果' },
      { sourceTaskId: 'parking-1', content: '停车场搜索工具结果' },
    ])
  })

  it('starts a conversation with backend-provided voice message ids', () => {
    const state = consoleReducer(initialConsoleState(), {
      type: 'startConversation',
      input: '打开空调',
      userMessageId: 'voice-user-backend-1',
      assistantMessageId: 'voice-assistant-backend-1',
      timestamp,
    })

    expect(state.messages).toMatchObject([
      {
        id: 'voice-user-backend-1',
        role: 'user',
        content: '打开空调',
        status: 'complete',
        createdAt: timestamp,
      },
      {
        id: 'voice-assistant-backend-1',
        messageId: 'voice-assistant-backend-1',
        role: 'assistant',
        content: '',
        status: 'streaming',
        createdAt: timestamp,
      },
    ])
    expect(state.activeAssistantMessageId).toBe('voice-assistant-backend-1')
  })

  it('creates the Agent placeholder directly from a voice final', () => {
    const state = consoleReducer(initialConsoleState(), {
      type: 'appendVoiceUserMessage',
      turnId: 'voice-turn-1',
      userMessageId: 'voice-user-1',
      assistantMessageId: 'voice-assistant-1',
      text: '查一下天气',
      timestamp,
    })

    expect(state.messages).toMatchObject([
      {
        id: 'voice-user-1',
        role: 'user',
        content: '查一下天气',
        voiceAssistantMessageId: 'voice-assistant-1',
      },
      {
        id: 'voice-assistant-1',
        role: 'assistant',
        status: 'streaming',
      },
    ])
    expect(state.registeredAssistantMessageIds).toEqual(['voice-assistant-1'])
    expect(state.runtimeTrace.entries).toMatchObject([{
      kind: 'user.submitted',
      messageId: 'voice-assistant-1',
    }])
  })

  it('appends Duplex feedback once even when its turn id is null', () => {
    const action = {
      type: 'appendVoiceFeedbackMessage' as const,
      turnId: null,
      feedbackId: 'voice-feedback-duplex',
      text: '我听着呢',
      timestamp,
    }

    let state = consoleReducer(initialConsoleState(), action)
    state = consoleReducer(state, action)

    expect(state.messages).toMatchObject([{
      id: 'voice-feedback-duplex',
      role: 'assistant',
      content: '我听着呢',
      status: 'complete',
      voiceMessageKind: 'quick-response',
    }])
    expect(state.messages[0]?.voiceTurnId).toBeUndefined()
    expect(state.messages).toHaveLength(1)
    expect(state.activeAssistantMessageId).toBeUndefined()
  })

  it('keeps registered ownership across multiple top-level spans with one backend id', () => {
    const firstDeltaAt = '2026-07-16T03:00:01.000Z'
    const firstDoneAt = '2026-07-16T03:00:02.000Z'
    const secondStartAt = '2026-07-16T03:00:03.000Z'
    const secondDeltaAt = '2026-07-16T03:00:04.000Z'
    const secondDoneAt = '2026-07-16T03:00:05.000Z'
    let state = consoleReducer(initialConsoleState(), {
      type: 'startConversation',
      input: 'multi step request',
      userMessageId: 'user-1',
      assistantMessageId: 'agent-1',
      timestamp: '2026-07-16T03:00:00.000Z',
    })

    expect(state.registeredAssistantMessageIds).toEqual(['agent-1'])

    state = consoleReducer(state, {
      type: 'event',
      event: {
        id: 'delta-1',
        type: 'agent.text.delta',
        messageId: 'agent-1',
        delta: 'first reply',
        timestamp: firstDeltaAt,
      },
    })
    state = consoleReducer(state, {
      type: 'event',
      event: {
        id: 'done-1',
        type: 'agent.text.done',
        messageId: 'agent-1',
        timestamp: firstDoneAt,
      },
    })
    expect(state.isPlaying).toBe(false)
    expect(state.registeredAssistantMessageIds).toEqual(['agent-1'])
    expect(state.acceptedPlaybackMessageId).toBe('agent-1')
    expect(state.acceptedPlaybackRevision).toBe(2)

    const afterFirstDone = state
    state = consoleReducer(state, {
      type: 'event',
      event: {
        id: 'late-delta-after-done',
        type: 'agent.text.delta',
        messageId: 'agent-1',
        delta: 'late content must be rejected',
        timestamp: '2026-07-16T03:00:02.500Z',
      },
    })
    expect(state.messages).toBe(afterFirstDone.messages)
    expect(state.runtimeTrace).toBe(afterFirstDone.runtimeTrace)
    expect(state.acceptedPlaybackRevision).toBe(2)

    state = consoleReducer(state, {
      type: 'event',
      event: {
        id: 'start-2',
        type: 'agent.text.start',
        messageId: 'agent-1',
        timestamp: secondStartAt,
      },
    })
    state = consoleReducer(state, {
      type: 'event',
      event: {
        id: 'delta-2',
        type: 'agent.text.delta',
        messageId: 'agent-1',
        delta: 'second reply',
        timestamp: secondDeltaAt,
      },
    })
    state = consoleReducer(state, {
      type: 'event',
      event: {
        id: 'done-2',
        type: 'agent.text.done',
        messageId: 'agent-1',
        timestamp: secondDoneAt,
      },
    })

    const assistantMessages = state.messages.filter((message) => message.role === 'assistant')
    expect(assistantMessages).toMatchObject([
      { id: 'agent-1', messageId: 'agent-1', content: 'first reply', status: 'complete' },
      { messageId: 'agent-1', content: 'second reply', status: 'complete' },
    ])
    expect(assistantMessages).toHaveLength(2)
    expect(new Set(assistantMessages.map((message) => message.id)).size).toBe(2)
    expect(state.isPlaying).toBe(false)
    expect(state.registeredAssistantMessageIds).toEqual(['agent-1'])
    expect(state.acceptedPlaybackMessageId).toBe('agent-1')
    expect(state.acceptedPlaybackRevision).toBe(4)
    expect(state.runtimeTrace.entries.filter(
      (entry) => entry.kind === 'agent.activity',
    )).toMatchObject([
      { messageId: 'agent-1', status: 'complete', timestamp: firstDeltaAt },
      { messageId: 'agent-1', status: 'complete', timestamp: secondStartAt },
    ])
  })

  it('rejects top-level agent events without a registered streaming placeholder', () => {
    const state = consoleReducer(initialConsoleState(), {
      type: 'event',
      event: {
        id: 'orphan-delta',
        type: 'agent.text.delta',
        messageId: 'orphan-assistant',
        delta: 'must not render',
        timestamp,
      },
    })

    expect(state.messages).toEqual([])
    expect(state.runtimeTrace.entries).toEqual([])
    expect(state.activeAssistantMessageId).toBeUndefined()
    expect(state.isPlaying).toBe(false)
    expect(state.registeredAssistantMessageIds).toEqual([])
    expect(state.acceptedPlaybackMessageId).toBeUndefined()
    expect(state.acceptedPlaybackRevision).toBe(0)
  })

  it('does not derive global playback from a streaming task-result assistant', () => {
    const state = consoleReducer(initialConsoleState(), {
      type: 'event',
      event: {
        id: 'task-result-delta',
        type: 'agent.text.delta',
        messageId: 'task-result-assistant',
        sourceTaskId: 'task-1',
        delta: 'background result',
        timestamp,
      },
    })

    expect(state.messages).toMatchObject([{
      messageId: 'task-result-assistant',
      sourceTaskId: 'task-1',
      status: 'streaming',
    }])
    expect(state.activeAssistantMessageId).toBeUndefined()
    expect(state.isPlaying).toBe(false)
  })

  it('updates the assistant timestamp when the waiting placeholder receives real content', () => {
    let state = consoleReducer(initialConsoleState(), {
      type: 'startConversation',
      input: 'request',
      userMessageId: 'user-1',
      assistantMessageId: 'agent-1',
      timestamp: '2026-06-16T10:00:00.000Z',
    })

    state = consoleReducer(state, {
      type: 'event',
      event: {
        id: 'delta-1',
        type: 'agent.text.delta',
        messageId: 'agent-1',
        delta: '真正的回复',
        timestamp: '2026-06-16T10:00:07.000Z',
      },
    })

    expect(state.messages[1]).toMatchObject({
      id: 'agent-1',
      content: '真正的回复',
      createdAt: '2026-06-16T10:00:07.000Z',
    })
  })

  it('does not stop the active stream when a secondary assistant message completes', () => {
    let state = consoleReducer(initialConsoleState(), {
      type: 'startConversation',
      input: 'request',
      userMessageId: 'user-1',
      assistantMessageId: 'agent-1',
    })

    state = consoleReducer(state, {
      type: 'event',
      event: {
        id: 'secondary-done',
        type: 'agent.text.done',
        messageId: 'agent-secondary',
        timestamp,
      },
    })

    expect(state.isPlaying).toBe(true)
  })

  it('projects task events into task state', () => {
    const state = consoleReducer(initialConsoleState(), {
      type: 'event',
      event: {
        id: 'task-created',
        type: 'task.created',
        timestamp,
        taskId: 'task-1',
        toolName: 'tool',
        title: 'tool',
        arguments: { value: true },
      },
    })

    expect(state.tasks.byId['task-1']).toMatchObject({
      taskId: 'task-1',
      status: 'pending',
      title: 'tool',
    })
  })

  it('selects tasks, stores toasts, and resets runtime state', () => {
    let state = consoleReducer(initialConsoleState(), { type: 'selectTask', taskId: 'task-1' })
    state = consoleReducer(state, {
      type: 'toast',
      toast: { id: 'toast-1', message: 'cancel rejected', level: 'info' },
    })

    expect(state.selectedTaskId).toBe('task-1')
    expect(state.toasts).toHaveLength(1)

    state = consoleReducer(state, { type: 'dismissToast', toastId: 'toast-1' })
    expect(state.toasts).toEqual([])

    state = consoleReducer(state, { type: 'reset' })
    expect(state).toEqual(initialConsoleState())
  })

  it('routes Plan events into planner state and reset clears the projection', () => {
    let state = initialConsoleState()
    state = consoleReducer(state, {
      type: 'event',
      event: {
        id: 'round-start',
        type: 'plact.round.start',
        timestamp,
        messageId: 'agent-1',
        round: 0,
      },
    })
    state = consoleReducer(state, {
      type: 'event',
      event: {
        id: 'plan-created',
        type: 'plan.created',
        timestamp,
        messageId: 'agent-1',
        round: 0,
        plan: {
          goal: 'search',
          raw: { goal: 'search' },
          steps: [{
            stepId: 'lookup',
            stepGoal: 'find a place',
            op: '地点搜索工具',
            dependsOn: [],
            rawInputs: { query: 'coffee' },
            outputSpec: { is_list: true, concept: { name: 'Place' } },
            successCheck: 'true',
          }],
        },
      },
    })

    expect(state.planner.activePageId).toBe('agent-1:0')
    expect(state.planner.pages[0].nodes[0]).toMatchObject({
      id: 'lookup',
      status: 'pending',
    })

    state = consoleReducer(state, { type: 'reset' })
    expect(state.planner).toEqual(initialPlannerState())
  })

  it('selects an existing Plan round page without duplicating graph state', () => {
    const first = {
      id: 'agent-1:0',
      messageId: 'agent-1',
      round: 0,
      title: 'Round 1',
      status: 'replanned' as const,
      nodes: [],
      edges: [],
      runnerErrors: [],
      roundErrors: [],
      createdAt: timestamp,
      updatedAt: timestamp,
    }
    const second = {
      ...first,
      id: 'agent-1:1',
      round: 1,
      title: 'Round 2',
      status: 'running' as const,
    }
    const state = {
      ...initialConsoleState(),
      planner: {
        pages: [first, second],
        activePageId: second.id,
        activeRoundByMessageId: { 'agent-1': 1 },
      },
    }

    const selected = consoleReducer(state, {
      type: 'selectPlanPage',
      pageId: first.id,
    })

    expect(selected.planner.activePageId).toBe(first.id)
    expect(selected.planner.pages).toEqual([first, second])
  })
})
