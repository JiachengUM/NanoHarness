/** 流式 ASR 体验（voice-test 内嵌小组件）：弹窗里点「开始收音」持续采集 → WS 直推后端 → 流式回显识别文本。 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Modal, Tag, message } from 'antd'
import { AudioOutlined, ClearOutlined, StopOutlined } from '@ant-design/icons'
import { BrowserVoiceAudio } from './audio-helper'
import styles from './asr-demo.module.less'

type AsrLine = { key: number; text: string }

type AsrServerEvent = {
  type: 'asr_started' | 'asr_delta' | 'asr_final' | 'asr_finished' | 'asr_error'
  text?: string
  message?: string
  code?: number
  audio_url?: string
}

type DemoStatus = 'idle' | 'recording' | 'stopping'

const STATUS_TAG: Record<DemoStatus, { color: string; label: string }> = {
  idle: { color: 'default', label: '未开始' },
  recording: { color: 'green', label: '识别中' },
  stopping: { color: 'processing', label: '收尾中' },
}

/** ASR 体验固定走 /api/voice_test/asr_stream：有 API 基址直连，否则走当前站点代理。 */
function getAsrStreamUrl(): string {
  const apiBase = import.meta.env.VITE_DEFAULT_API_URL as string | undefined
  if (apiBase && apiBase.startsWith('http')) {
    return `${apiBase.replace(/^http/, 'ws').replace(/\/$/, '')}/voice_test/asr_stream`
  }
  const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${wsProto}//${window.location.host}/api/voice_test/asr_stream`
}

type AsrDemoProps = {
  open: boolean
  onClose: () => void
}

const AsrDemo: React.FC<AsrDemoProps> = ({ open, onClose }) => {
  const [messageApi, contextHolder] = message.useMessage()
  const [status, setStatus] = useState<DemoStatus>('idle')
  const [lines, setLines] = useState<AsrLine[]>([])
  const [current, setCurrent] = useState('')
  const [error, setError] = useState('')
  const [audioUrl, setAudioUrl] = useState('')
  const wsRef = useRef<WebSocket | null>(null)
  const audioRef = useRef<BrowserVoiceAudio | null>(null)
  const bodyRef = useRef<HTMLDivElement | null>(null)
  const statusRef = useRef<DemoStatus>('idle')
  const keyRef = useRef(0)

  useEffect(() => {
    statusRef.current = status
  }, [status])

  const cleanup = useCallback((nextStatus: DemoStatus = 'idle') => {
    const ws = wsRef.current
    if (ws) {
      ws.onopen = null
      ws.onmessage = null
      ws.onerror = null
      ws.onclose = null
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close()
      }
      wsRef.current = null
    }
    audioRef.current?.stop()
    audioRef.current = null
    setCurrent('')
    setStatus(nextStatus)
  }, [])

  // 组件卸载时释放麦克风与 WS 连接
  useEffect(() => cleanup, [cleanup])

  // 新识别内容自动滚到底部
  useEffect(() => {
    const el = bodyRef.current
    if (el) {
      el.scrollTop = el.scrollHeight
    }
  }, [lines, current])

  // 关闭弹窗：先清理收音与 WS，再通知父级关闭
  const handleClose = () => {
    cleanup('idle')
    onClose()
  }

  const handleStart = async () => {
    if (statusRef.current !== 'idle') {
      return
    }
    const audio = new BrowserVoiceAudio()
    try {
      await audio.init()
    } catch {
      messageApi.error('无法访问麦克风')
      return
    }
    audioRef.current = audio
    setError('')
    setAudioUrl('')
    setStatus('recording')
    setCurrent('识别中…')

    const ws = new WebSocket(getAsrStreamUrl())
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    ws.onopen = () => {
      audio.startCapture((chunk) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(chunk)
        }
      })
      audio.setListening(true)
    }

    ws.onmessage = (event) => {
      if (wsRef.current !== ws) {
        return
      }
      const data = JSON.parse(event.data as string) as AsrServerEvent
      if (data.type === 'asr_delta' && data.text) {
        setCurrent(data.text)
      } else if (data.type === 'asr_final' && data.text) {
        const text = data.text.trim()
        if (text) {
          setLines((prev) => [...prev, { key: ++keyRef.current, text }])
        }
        setCurrent('')
      } else if (data.type === 'asr_finished') {
        setAudioUrl(data.audio_url || '')
        cleanup('idle')
      } else if (data.type === 'asr_error') {
        setError(data.message || `ASR 错误 (${data.code})`)
        messageApi.error(data.message || 'ASR 识别出错')
        cleanup('idle')
      }
    }

    ws.onerror = () => {
      messageApi.error('WebSocket 连接失败')
      cleanup('idle')
    }

    ws.onclose = () => {
      if (wsRef.current === ws) {
        cleanup('idle')
      }
    }
  }

  const handleStop = () => {
    if (statusRef.current !== 'recording') {
      return
    }
    // 先停收音，避免 stop 后仍有音频上行；WS 保持连接等服务端收尾事件
    audioRef.current?.setListening(false)
    setStatus('stopping')
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'stop' }))
    } else {
      cleanup('idle')
    }
  }

  const handleClear = () => {
    setLines([])
    setCurrent('')
    setError('')
    setAudioUrl('')
  }

  const isBusy = status !== 'idle'
  const tag = STATUS_TAG[status]

  return (
    <Modal open={open} title="流式 ASR 体验" onCancel={handleClose} footer={null} width={640}>
      {contextHolder}
      <div className={styles.root}>
        <div className={styles.toolbar}>
          <Button type="primary" icon={<AudioOutlined />} disabled={isBusy} onClick={handleStart}>
            开始收音
          </Button>
          <Button icon={<StopOutlined />} disabled={status !== 'recording'} onClick={handleStop}>
            停止识别
          </Button>
          <Button icon={<ClearOutlined />} disabled={lines.length === 0 && !current} onClick={handleClear}>
            清空
          </Button>
          <Tag color={tag.color}>{tag.label}</Tag>
        </div>
        {error && <div className={styles.error}>{error}</div>}
        {audioUrl && (
          <div className={styles.audioBox}>
            <div className={styles.audioLabel}>本次识别音频（已保存）：</div>
            <audio controls src={audioUrl} />
          </div>
        )}
        <div className={styles.body} ref={bodyRef}>
          {lines.map((line) => (
            <div key={line.key} className={styles.line}>
              {line.text}
            </div>
          ))}
          {current && <div className={`${styles.line} ${styles.current}`}>{current}</div>}
          {lines.length === 0 && !current && (
            <div className={styles.empty}>点击「开始收音」后说话，识别结果将实时显示在这里。</div>
          )}
        </div>
      </div>
    </Modal>
  )
}

export default AsrDemo
