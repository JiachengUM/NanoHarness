import { readFileSync } from 'node:fs'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import {
  ChatPanel,
  getAssistantResponseCount,
  getChatScrollTarget,
  isChatAtLatest,
} from './ChatPanel'

describe('chat scroll behavior', () => {
  it('follows content growth when the user was near the previous bottom', () => {
    expect(getChatScrollTarget({
      clientHeight: 300,
      scrollHeight: 760,
      currentScrollTop: 400,
      previousScrollHeight: 700,
      isInitial: false,
    })).toEqual({ shouldScroll: true, top: 460 })
  })

  it('preserves explicit history intent when previous geometry is stale', () => {
    expect(getChatScrollTarget({
      clientHeight: 300,
      scrollHeight: 900,
      currentScrollTop: 500,
      previousScrollHeight: 700,
      isInitial: false,
      wasFollowingLatest: false,
    })).toEqual({ shouldScroll: false, top: 500 })
  })

  it('follows explicit latest intent when previous geometry is stale', () => {
    expect(getChatScrollTarget({
      clientHeight: 300,
      scrollHeight: 900,
      currentScrollTop: 100,
      previousScrollHeight: 700,
      isInitial: false,
      wasFollowingLatest: true,
    })).toEqual({ shouldScroll: true, top: 600 })
  })

  it('preserves the user position when they are viewing older messages', () => {
    expect(getChatScrollTarget({
      clientHeight: 300,
      scrollHeight: 760,
      currentScrollTop: 120,
      previousScrollHeight: 700,
      isInitial: false,
    })).toEqual({ shouldScroll: false, top: 120 })
  })

  it('treats positions within the latest-message threshold as current', () => {
    expect(isChatAtLatest({
      clientHeight: 300,
      scrollHeight: 760,
      currentScrollTop: 428,
    })).toBe(true)
    expect(isChatAtLatest({
      clientHeight: 300,
      scrollHeight: 760,
      currentScrollTop: 400,
    })).toBe(false)
  })

  it('scrolls an initial render to the maximum position', () => {
    expect(getChatScrollTarget({
      clientHeight: 300,
      scrollHeight: 760,
      currentScrollTop: 0,
      previousScrollHeight: 760,
      isInitial: true,
    })).toEqual({ shouldScroll: true, top: 460 })
  })

  it('preserves a valid history position when content shrinks', () => {
    expect(getChatScrollTarget({
      clientHeight: 300,
      scrollHeight: 800,
      currentScrollTop: 120,
      previousScrollHeight: 1000,
      isInitial: false,
    })).toEqual({ shouldScroll: false, top: 120 })
  })

  it('preserves a valid near-bottom position when content shrinks', () => {
    expect(getChatScrollTarget({
      clientHeight: 300,
      scrollHeight: 780,
      currentScrollTop: 470,
      previousScrollHeight: 800,
      isInitial: false,
    })).toEqual({ shouldScroll: false, top: 470 })
  })

  it('clamps the position to the valid maximum when content shrinks', () => {
    expect(getChatScrollTarget({
      clientHeight: 300,
      scrollHeight: 420,
      currentScrollTop: 600,
      previousScrollHeight: 1200,
      isInitial: false,
    })).toEqual({ shouldScroll: true, top: 120 })
  })
})

describe('ChatPanel', () => {
  it('waits for visible Agent content before unlocking a guided next step', () => {
    const emptyStreaming: Parameters<typeof getAssistantResponseCount>[0] = [{
      id: 'agent-empty',
      role: 'assistant',
      content: '',
      status: 'streaming',
      createdAt: '2026-07-20T01:00:00.000Z',
    }]
    const visibleResponse = [{
      ...emptyStreaming[0],
      content: '任务已经开始查询。',
    }]

    expect(getAssistantResponseCount(emptyStreaming)).toBe(0)
    expect(getAssistantResponseCount(visibleResponse)).toBe(1)
  })

  it.each(['listening', 'processing'] as const)(
    'keeps the microphone control stable while the open session is %s',
    (voicePhase) => {
      const markup = renderToStaticMarkup(
        <ChatPanel
          messages={[]}
          liveInput=""
          isPlaying={voicePhase === 'processing'}
          connected
          voicePhase={voicePhase}
          voiceInputLocked
          voiceMicrophoneOpen
          modeResetting={false}
          onLiveInputChange={vi.fn()}
          onStartLive={vi.fn()}
          onToggleVoice={vi.fn()}
        />,
      )

      expect(markup).toContain('class="icon-button voice-button active"')
      expect(markup).toContain('class="voice-wave"')
      expect(markup).toContain('class="icon-button voice-close-button"')
      expect(markup).toContain('aria-label="关闭语音输入"')
      expect(markup).not.toContain('voice-attention')
      expect(markup).not.toContain('等待唤醒')
    },
  )

  it('keeps the restored microphone close action compact and visually secondary', () => {
    const css = readFileSync(new URL('../styles.css', import.meta.url), 'utf8')
    const closeRule = css.match(
      /\.icon-button\.voice-close-button\s*\{([^}]*)\}/s,
    )?.[1] ?? ''

    expect(closeRule).toMatch(/width:\s*32px/)
    expect(closeRule).toMatch(/height:\s*32px/)
    expect(closeRule).toMatch(/background:\s*transparent/)
  })

  it('renders assistant replies as safe GitHub-flavored Markdown while keeping user text literal', () => {
    const markup = renderToStaticMarkup(
      <ChatPanel
        messages={[
          {
            id: 'user-markdown',
            role: 'user',
            content: '**不要解释用户输入**',
            status: 'complete',
            createdAt: '2026-06-16T10:30:00.000Z',
          },
          {
            id: 'agent-markdown',
            messageId: 'agent-markdown',
            role: 'assistant',
            content: [
              '## 搜索结果',
              '',
              '- **地点 A**',
              '- 使用 `poi_search`',
              '',
              '| 名称 | 状态 |',
              '| --- | --- |',
              '| 地点 A | 完成 |',
              '',
              '[查看详情](https://example.com)',
              '',
              '[危险链接](javascript:alert(1))',
              '',
              '<script>alert("unsafe")</script>',
            ].join('\n'),
            status: 'complete',
            createdAt: '2026-06-16T10:30:01.000Z',
          },
        ]}
        liveInput=""
        isPlaying={false}
        connected
        voicePhase="idle"
        voiceInputLocked={false}
        voiceMicrophoneOpen={false}
        modeResetting={false}
        onLiveInputChange={vi.fn()}
        onStartLive={vi.fn()}
        onToggleVoice={vi.fn()}
      />,
    )

    expect(markup).toContain('<p>**不要解释用户输入**</p>')
    expect(markup).toContain('class="message-markdown"')
    expect(markup).toContain('<h2>搜索结果</h2>')
    expect(markup).toContain('<strong>地点 A</strong>')
    expect(markup).toContain('<code>poi_search</code>')
    expect(markup).toContain('<table>')
    expect(markup).toContain(
      '<a href="https://example.com" target="_blank" rel="noreferrer noopener">查看详情</a>',
    )
    expect(markup).not.toContain('<script>')
    expect(markup).not.toContain('javascript:')
    expect(markup).toContain(
      '&lt;script&gt;alert(&quot;unsafe&quot;)&lt;/script&gt;',
    )
  })

  it('keeps the streaming cursor attached to the final Markdown paragraph', () => {
    const markup = renderToStaticMarkup(
      <ChatPanel
        messages={[
          {
            id: 'agent-streaming-markdown',
            messageId: 'agent-streaming-markdown',
            role: 'assistant',
            content: '**正在**输出结果',
            status: 'streaming',
            createdAt: '2026-06-16T10:30:01.000Z',
          },
        ]}
        liveInput=""
        isPlaying={false}
        connected
        voicePhase="idle"
        voiceInputLocked={false}
        voiceMicrophoneOpen={false}
        modeResetting={false}
        onLiveInputChange={vi.fn()}
        onStartLive={vi.fn()}
        onToggleVoice={vi.fn()}
      />,
    )
    const css = readFileSync(new URL('../styles.css', import.meta.url), 'utf8')

    expect(markup).toContain('class="message-markdown is-streaming"')
    expect(markup).toContain(
      '<p><strong>正在</strong>输出结果</p></div><span class="cursor">▌</span>',
    )
    expect(css).toMatch(
      /\.message-markdown\.is-streaming\s*\{[^}]*display:\s*contents;/s,
    )
    expect(css).toMatch(
      /\.message-markdown\.is-streaming > p:last-child\s*\{[^}]*display:\s*inline;[^}]*margin-bottom:\s*0;/s,
    )
  })

  it('labels a background task result with its tool but not the original request', () => {
    const originalRequest = '找徐汇滨江3公里内、停车方便的餐厅'
    const markup = renderToStaticMarkup(
      <ChatPanel
        messages={[
          {
            id: 'user-origin',
            role: 'user',
            content: originalRequest,
            status: 'complete',
            createdAt: '2026-06-16T10:30:00.000Z',
          },
          {
            id: 'agent-origin',
            messageId: 'agent-origin',
            role: 'assistant',
            content: '任务已提交',
            status: 'complete',
            createdAt: '2026-06-16T10:30:01.000Z',
          },
          {
            id: 'task-result-poi-1',
            messageId: 'task-result-poi-1',
            role: 'assistant',
            content: '找到 3 家候选餐厅。',
            status: 'complete',
            createdAt: '2026-06-16T10:31:01.000Z',
            sourceTaskId: 'poi-1',
            sourceTaskTitle: '地点搜索工具',
          },
        ]}
        liveInput=""
        isPlaying={false}
        connected
        voicePhase="idle"
        voiceInputLocked={false}
        voiceMicrophoneOpen={false}
        modeResetting={false}
        onLiveInputChange={vi.fn()}
        onStartLive={vi.fn()}
        onToggleVoice={vi.fn()}
      />,
    )

    expect(markup).toContain('后台任务结果 · 地点搜索工具')
    expect(markup).not.toContain(`来源：“${originalRequest}”`)
    expect(markup).not.toContain(`title="${originalRequest}"`)
    expect(markup).not.toContain('task-result-origin')
  })

  it('renders svg avatars and timestamp-only subtitles outside message bubbles', () => {
    const markup = renderToStaticMarkup(
      <ChatPanel
        messages={[
          {
            id: 'user-1',
            role: 'user',
            content: '帮我规划路线',
            status: 'complete',
            createdAt: '2026-06-16T10:30:00.000Z',
          },
          {
            id: 'agent-1',
            messageId: 'agent-1',
            role: 'assistant',
            content: '正在拆解任务',
            status: 'complete',
            createdAt: '2026-06-16T10:30:01.000Z',
          },
          {
            id: 'agent-2',
            messageId: 'agent-2',
            role: 'assistant',
            content: '',
            status: 'streaming',
            createdAt: '2026-06-16T10:30:02.000Z',
          },
        ]}
        liveInput=""
        isPlaying={false}
        connected
        voicePhase="idle"
        voiceInputLocked={false}
        voiceMicrophoneOpen={false}
        modeResetting={false}
        onLiveInputChange={vi.fn()}
        onStartLive={vi.fn()}
        onToggleVoice={vi.fn()}
      />,
    )

    expect(markup).toContain('aria-label="用户头像"')
    expect(markup).toContain('aria-label="Agent头像"')
    expect(markup).toContain('role="img"')
    expect(markup).toContain('<svg')
    expect(markup).not.toContain('用户 · ')
    expect(markup).not.toContain('Agent · ')
    expect(markup).not.toContain('message-meta')
    expect(markup).not.toContain('>...</p>')
    expect(markup).toContain('class="message-waiting"')
    expect(markup).toContain('class="message-waiting-spinner"')
    expect(markup).toContain('aria-label="Agent 正在回复"')
    expect(markup).toContain('class="message-timestamp"')
    expect(markup).toContain('dateTime="2026-06-16T10:30:00.000Z"')
    expect(markup).toContain('dateTime="2026-06-16T10:30:01.000Z"')
    expect(markup).toContain('dateTime="2026-06-16T10:30:02.000Z"')

    const userBubbleClose = markup.indexOf('</div><time class="message-timestamp" dateTime="2026-06-16T10:30:00.000Z"')
    const agentBubbleClose = markup.indexOf('</div><time class="message-timestamp" dateTime="2026-06-16T10:30:01.000Z"')
    expect(userBubbleClose).toBeGreaterThan(-1)
    expect(agentBubbleClose).toBeGreaterThan(-1)
  })

  it('shows active assistant speech on the targeted assistant bubble instead of the microphone control', () => {
    const markup = renderToStaticMarkup(
      <ChatPanel
        messages={[
          {
            id: 'user-1',
            role: 'user',
            content: '讲一下结果',
            status: 'complete',
            createdAt: '2026-06-16T10:30:00.000Z',
          },
          {
            id: 'agent-1',
            messageId: 'agent-1',
            role: 'assistant',
            content: '这是当前回复',
            status: 'streaming',
            createdAt: '2026-06-16T10:30:01.000Z',
          },
        ]}
        liveInput=""
        isPlaying={false}
        connected
        voicePhase="idle"
        voiceInputLocked={false}
        voiceMicrophoneOpen={false}
        modeResetting={false}
        speakingAssistantMessageId="agent-1"
        onLiveInputChange={vi.fn()}
        onStartLive={vi.fn()}
        onToggleVoice={vi.fn()}
      />,
    )

    expect(markup).toContain('aria-label="开启语音输入"')
    expect(markup).toContain('正在播报')
    expect(markup).toContain('class="message-row assistant speaking"')
    expect(markup).toContain('class="message-avatar assistant speaking"')
  })

  it('keeps speech highlight on the playback target when a newer assistant bubble appears', () => {
    const markup = renderToStaticMarkup(
      <ChatPanel
        messages={[
          {
            id: 'agent-1',
            messageId: 'agent-1',
            role: 'assistant',
            content: '这是正在播的回复',
            status: 'complete',
            createdAt: '2026-06-16T10:30:01.000Z',
          },
          {
            id: 'agent-2',
            messageId: 'agent-2',
            role: 'assistant',
            content: '这是更新出来的新气泡',
            status: 'streaming',
            createdAt: '2026-06-16T10:30:02.000Z',
          },
        ]}
        liveInput=""
        isPlaying
        connected
        voicePhase="idle"
        voiceInputLocked={false}
        voiceMicrophoneOpen={false}
        modeResetting={false}
        speakingAssistantMessageId="agent-1"
        onLiveInputChange={vi.fn()}
        onStartLive={vi.fn()}
        onToggleVoice={vi.fn()}
      />,
    )

    const speakingRowIndex = markup.indexOf('class="message-row assistant speaking"')
    expect(speakingRowIndex).toBeGreaterThan(-1)
    expect(speakingRowIndex).toBeLessThan(markup.indexOf('这是正在播的回复'))
    expect(markup.indexOf('class="message-row assistant speaking"', speakingRowIndex + 1)).toBe(-1)
    expect(markup).toContain('这是更新出来的新气泡')
  })

  it('marks interrupted assistant messages', () => {
    const markup = renderToStaticMarkup(
      <ChatPanel
        messages={[
          {
            id: 'agent-1',
            messageId: 'agent-1',
            role: 'assistant',
            content: '前一轮还没说完',
            status: 'interrupted',
            createdAt: '2026-06-16T10:30:03.000Z',
          },
        ]}
        liveInput=""
        isPlaying={false}
        connected
        voicePhase="idle"
        voiceInputLocked={false}
        voiceMicrophoneOpen={false}
        modeResetting={false}
        onLiveInputChange={vi.fn()}
        onStartLive={vi.fn()}
        onToggleVoice={vi.fn()}
      />,
    )

    expect(markup).toContain('前一轮还没说完')
    expect(markup).toContain('已被打断')
    expect(markup).toContain('class="message-interrupted"')
  })

  it('locks new input, voice controls, and capability trials during a mode reset', () => {
    const markup = renderToStaticMarkup(
      <ChatPanel
        messages={[]}
        liveInput="must not submit"
        isPlaying={false}
        connected
        voicePhase="idle"
        voiceInputLocked={false}
        voiceMicrophoneOpen={false}
        modeResetting
        onLiveInputChange={vi.fn()}
        onStartLive={vi.fn()}
        onToggleVoice={vi.fn()}
      />,
    )

    expect(markup.match(/disabled=""/g)).toHaveLength(6)
    expect(markup).toContain('aria-label="live agent input"')
    expect(markup).toContain('readOnly=""')
  })

})
