import { describe, expect, it, vi } from 'vitest'
import {
  buildBrowserLatencyTrace,
  traceBrowserLatency,
} from './latencyTrace'

describe('browser latency trace', () => {
  it('uses the browser monotonic clock and only emits correlation fields', () => {
    expect(buildBrowserLatencyTrace('ui.submit', {
      command_id: 'cmd-1',
      command: 'agent.run',
      message_id: 'agent-1',
      origin_message_id: 'agent-origin',
      task_id: 'task-1',
      session_id: 'sess-1',
      generation: 7,
    }, 12.5)).toEqual({
      event: 'ui.submit',
      clock: 'browser',
      at_ms: 12.5,
      command_id: 'cmd-1',
      command: 'agent.run',
      message_id: 'agent-1',
      origin_message_id: 'agent-origin',
      task_id: 'task-1',
      session_id: 'sess-1',
      generation: 7,
    })
  })

  it('writes a structured console.info record', () => {
    const info = vi.spyOn(console, 'info').mockImplementation(() => undefined)

    const record = traceBrowserLatency('task.cancel.sent', { task_id: 'task-1' })

    expect(info).toHaveBeenCalledWith('[v2-latency]', record)
    expect(record.at_ms).toEqual(expect.any(Number))
    info.mockRestore()
  })
})
