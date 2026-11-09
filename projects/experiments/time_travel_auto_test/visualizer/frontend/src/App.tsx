/**
 * App：接线层——client（WS 事件流）→ reducer → 三面板投影。
 * 对齐 v2_frontend 的「事件即 action」模式：App 只做接线，不做业务。
 */
import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
  type CSSProperties,
} from 'react'
import {
  createVisualizerClient,
  type VisualizerClient,
} from './adapters/visualizerClient'
import {
  consoleReducer,
  initialConsoleState,
} from './app/consoleReducer'
import {
  buildTimeScale,
  clampPanX,
  computeLiveWindowMs,
  computeOverlaps,
  followCursorView,
  formatDuration,
  projectCarState,
  projectDialogue,
  projectLiveSpans,
  projectTimelineSpans,
  projectToolSpans,
  zoomReplayView,
  type ReplayView,
} from './app/projections'
import { useNowTicker } from './app/useNowTicker'
import { usePlaybackEngine } from './app/usePlaybackEngine'
import { RunConsole } from './components/RunConsole'
import type { AssistantKind } from './components/RunConsole'
import { ChatStream } from './components/ChatStream'
import { TimelineLanes } from './components/TimelineLanes'
import { CarStatePanel } from './components/CarStatePanel'
import { VerdictPanel } from './components/VerdictPanel'
import { PanelResizer } from './components/PanelResizer'
import { normalizeEvent, type EventEnvelope } from './domain/events'
import { errorMessage } from './utils/unknown'
import './styles.css'

// ---------------- 面板布局（用户拖拽调整 + localStorage 持久化） ----------------

const LAYOUT_STORAGE_KEY = 'ttat.rightColumnLayout'
const PANEL_MIN_PX = 120
const PANEL_MAX_PX = 1200
const DEFAULT_TIMELINE_H = 360
const DEFAULT_CAR_H = 200
const DEFAULT_LEFT_W = 720
/** 对话流最小宽度（px）——保证气泡可读。 */
const LEFT_W_MIN_PX = 360

interface RightColumnLayout {
  timelineH?: number
  carH?: number
  leftW?: number
}

function loadLayout(): RightColumnLayout {
  try {
    const raw = localStorage.getItem(LAYOUT_STORAGE_KEY)
    return raw ? (JSON.parse(raw) as RightColumnLayout) : {}
  } catch {
    return {}
  }
}

function clampPanelHeight(px: number): number {
  return Math.min(PANEL_MAX_PX, Math.max(PANEL_MIN_PX, Math.round(px)))
}

export default function App() {
  const [state, dispatch] = useReducer(consoleReducer, undefined, initialConsoleState)
  const clientRef = useRef<VisualizerClient | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const client = useMemo(() => {
    const created = createVisualizerClient()
    clientRef.current = created
    return created
  }, [])

  // 事件流 / 连接状态 / 错误 → dispatch；发起 WS 连接
  useEffect(() => {
    client.onEvent((event) => dispatch({ type: 'event', event }))
    client.onConnectionChange((connection) =>
      dispatch({ type: 'connection', state: connection }),
    )
    client.onError((message) => dispatch({ type: 'localError', message }))
    client.connect().catch((error: unknown) => {
      dispatch({ type: 'localError', message: `连接失败: ${errorMessage(error)}` })
    })
    return () => {
      client.dispose()
      clientRef.current = null
    }
  }, [client])

  // 连接后拉取 case 列表
  useEffect(() => {
    if (state.connection !== 'open') {
      return
    }
    let active = true
    client
      .listCases()
      .then((cases) => {
        if (active) {
          dispatch({ type: 'casesLoaded', cases })
        }
      })
      .catch((error: unknown) => {
        if (active) {
          dispatch({ type: 'localError', message: `获取 case 列表失败: ${errorMessage(error)}` })
        }
      })
    return () => {
      active = false
    }
  }, [client, state.connection])

  // toast 自动消失
  useEffect(() => {
    if (state.toasts.length === 0) return
    const timer = setTimeout(() => {
      dispatch({ type: 'dismissToast', toastId: state.toasts[0].id })
    }, 4000)
    return () => clearTimeout(timer)
  }, [state.toasts])

  const handleStart = useCallback(
    (caseId: string, assistantKind: AssistantKind) => {
      dispatch({ type: 'resetRun' })
      client
        .runCase({ caseId, assistantKind })
        .catch((error: unknown) => {
          dispatch({
            type: 'localError',
            message: `运行失败: ${errorMessage(error)}`,
          })
        })
    },
    [client],
  )

  const handleStop = useCallback(() => {
    client.stopCase().catch((error: unknown) => {
      dispatch({
        type: 'localError',
        message: `停止失败: ${errorMessage(error)}`,
      })
    })
  }, [client])

  const handleJudge = useCallback(() => {
    dispatch({ type: 'judgeRequested' })
    client.judgeCase().catch((error: unknown) => {
      dispatch({
        type: 'localError',
        message: `发起评判失败: ${errorMessage(error)}`,
      })
    })
  }, [client])

  // 导入离线事件流快照（probe_event_stream.py 落盘的信封数组），做回放对比。
  // 信封与 WS 下行 {kind:"event", event: 信封} 完全同构，逐条 normalizeEvent →
  // dispatch，复用现有回放投影（case_started 起播、case_finished 进入 paused 回放）。
  const handleImportFile = useCallback(
    (file: File) => {
      const reader = new FileReader()
      reader.onload = () => {
        try {
          const raw = JSON.parse(String(reader.result))
          const envelopes = Array.isArray(raw) ? raw : []
          dispatch({ type: 'resetRun' })
          for (const item of envelopes) {
            const envelope = item as EventEnvelope
            if (
              envelope &&
              typeof envelope.seq === 'number' &&
              typeof envelope.kind === 'string'
            ) {
              dispatch({ type: 'event', event: normalizeEvent(envelope) })
            }
          }
        } catch (error: unknown) {
          dispatch({
            type: 'localError',
            message: `导入失败: ${errorMessage(error)}`,
          })
        }
      }
      reader.onerror = () => {
        dispatch({ type: 'localError', message: '读取事件流文件失败' })
      }
      reader.readAsText(file)
    },
    [dispatch],
  )

  const handleImportClick = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  // 投影（纯函数，reducer 状态 → 各面板视图模型）
  // 回放游标：run 结束后由 playback.cursorMs 驱动（null = 实时模式，走最新语义）
  const playbackActive =
    state.run.status === 'finished' ||
    state.run.status === 'cancelled' ||
    state.run.status === 'error'
  const cursorMs = playbackActive ? state.playback.cursorMs : null

  // 实时虚拟时钟（双时间戳外推，100ms 重绘）：驱动时间轴伸长、live 增长条、
  // 执行中工具条右端推进——"说话开始就能看到不断变长的条"的坐标系
  const nowMs = useNowTicker(
    state.run.status === 'running',
    state.events,
    state.t0,
  )

  // 时间线视窗状态：泳道轨道像素宽（live 窗口自适应）+ 回放 zoom/pan
  const [viewportWidth, setViewportWidth] = useState(0)
  const [replayView, setReplayView] = useState<ReplayView>({ zoom: 1, panX: 0 })

  const entries = useMemo(
    () => projectDialogue(state, cursorMs),
    [state, cursorMs],
  )
  // 剧本预设事件的未来区分界：实时 = 当前虚拟时刻；回放 = 游标
  // （游标之后的预设事件显示为竖线，已发生的由落盘事件接管）
  const axisMs = playbackActive ? state.playback.cursorMs : (nowMs ?? 0)
  // 时间线刻度（双模式）：live = 中央轴线滑动窗口（20s 基准，宽屏自适应）；
  // replay = 全程分段映射（快进压缩）后经 zoom/pan 视窗变换
  const scale = useMemo(
    () =>
      buildTimeScale(
        state.events,
        state.t0,
        playbackActive
          ? {
              mode: 'replay',
              cursorMs: state.playback.cursorMs,
              zoom: replayView.zoom,
              panX: replayView.panX,
            }
          : {
              mode: 'live',
              axisMs: nowMs ?? 0,
              windowMs: computeLiveWindowMs(viewportWidth),
              widthPx: viewportWidth,
            },
      ),
    [
      state.events,
      state.t0,
      playbackActive,
      state.playback.cursorMs,
      replayView,
      nowMs,
      viewportWidth,
    ],
  )
  const spans = useMemo(
    () => projectTimelineSpans(state.events, state.t0, state.scriptPlan, axisMs),
    [state.events, state.t0, state.scriptPlan, axisMs],
  )
  // 工具子泳道：实时尾随 nowMs，回放尾随游标（执行中的条随时间/游标增长）
  const toolSpans = useMemo(
    () => projectToolSpans(state.events, state.t0, cursorMs, playbackActive ? null : nowMs),
    [state.events, state.t0, cursorMs, playbackActive, nowMs],
  )
  // live 增长条：正在说的话（开口 → now）；回放模式不适用
  const liveSpans = useMemo(
    () => projectLiveSpans(state, playbackActive ? null : nowMs),
    [state, playbackActive, nowMs],
  )
  const overlaps = useMemo(
    () => computeOverlaps(state.events, state.t0),
    [state.events, state.t0],
  )
  // 车态时间机：实时模式（cursorMs=null）全量合并 = 最新状态；
  // 回放模式只合并 mock_time ≤ 游标 的 car_set_state
  const carView = useMemo(
    () => projectCarState(state.events, state.t0, cursorMs),
    [state.events, state.t0, cursorMs],
  )

  // rAF 回放引擎：playing 时按倍速推进游标（到终点自动暂停）
  usePlaybackEngine(state.playback, scale.endMs, dispatch)

  // 回放控制（视频播放器语义）
  const handleScrub = useCallback((cursorMs: number) => {
    dispatch({ type: 'playbackScrub', cursorMs })
  }, [])

  const handlePlayPause = useCallback(() => {
    if (state.playback.mode === 'playing') {
      dispatch({ type: 'playbackPause' })
      return
    }
    // 游标已在终点 → 从头播放（视频习惯）
    const rewind = scale.endMs > 0 && state.playback.cursorMs >= scale.endMs
    dispatch({ type: 'playbackPlay', rewind })
  }, [scale.endMs, state.playback])

  const handleSpeed = useCallback((speed: number) => {
    dispatch({ type: 'playbackSpeed', speed })
  }, [])

  // 回放视窗控制：缩放（锚定游标）+ 平移 + 轨道宽度上报
  const handleZoom = useCallback(
    (zoom: number) => {
      setReplayView((view) =>
        zoomReplayView(view, zoom, scale.domainX(state.playback.cursorMs)),
      )
    },
    [scale, state.playback.cursorMs],
  )

  const handlePan = useCallback((panX: number) => {
    setReplayView((view) => ({ zoom: view.zoom, panX: clampPanX(panX, view.zoom) }))
  }, [])

  const handleViewportWidth = useCallback((widthPx: number) => {
    setViewportWidth((current) => (current === widthPx ? current : widthPx))
  }, [])

  // 新 run 开始：回放视窗重置为全程一览（zoom=1）
  useEffect(() => {
    if (state.run.status === 'running') {
      setReplayView({ zoom: 1, panX: 0 })
    }
  }, [state.run.status])

  // 播放中视窗自动跟随：游标滑出视窗 → 平移使其居中（zoom=1 恒可见，无操作）
  useEffect(() => {
    if (state.playback.mode !== 'playing') return
    const cursorDomainX = scale.domainX(state.playback.cursorMs)
    setReplayView((view) => followCursorView(view, cursorDomainX))
  }, [state.playback.mode, state.playback.cursorMs, scale])

  // 右栏面板高度（用户拖拽调整；localStorage 持久化适配不同屏幕）
  const [timelineHeight, setTimelineHeight] = useState(() =>
    clampPanelHeight(loadLayout().timelineH ?? DEFAULT_TIMELINE_H),
  )
  const [carStateHeight, setCarStateHeight] = useState(() =>
    clampPanelHeight(loadLayout().carH ?? DEFAULT_CAR_H),
  )
  // 对话流宽度（左右拖拽调整；右侧观察区吃掉剩余空间）
  const [leftWidth, setLeftWidth] = useState(() =>
    Math.max(LEFT_W_MIN_PX, Math.round(loadLayout().leftW ?? DEFAULT_LEFT_W)),
  )

  useEffect(() => {
    try {
      localStorage.setItem(
        LAYOUT_STORAGE_KEY,
        JSON.stringify({
          timelineH: timelineHeight,
          carH: carStateHeight,
          leftW: leftWidth,
        }),
      )
    } catch {
      // localStorage 不可用（隐私模式等）：仅本次会话内生效
    }
  }, [timelineHeight, carStateHeight, leftWidth])

  const handleTimelineResize = useCallback((deltaPx: number) => {
    setTimelineHeight((h) => clampPanelHeight(h + deltaPx))
  }, [])

  const handleCarStateResize = useCallback((deltaPx: number) => {
    setCarStateHeight((h) => clampPanelHeight(h + deltaPx))
  }, [])

  const handleLeftResize = useCallback((deltaPx: number) => {
    setLeftWidth((w) => Math.max(LEFT_W_MIN_PX, Math.round(w + deltaPx)))
  }, [])

  return (
    <main className="app-shell">
      {state.toasts.length > 0 && (
        <div className="toast-container">
          {state.toasts.map((toast) => (
            <div key={toast.id} className={`toast toast-${toast.level}`}>
              <span>{toast.message}</span>
              <button
                type="button"
                aria-label="关闭提示"
                onClick={() => dispatch({ type: 'dismissToast', toastId: toast.id })}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
      <header className="app-header">
        <div>
          <p className="eyebrow">TIME TRAVEL AUTO TEST</p>
          <h1>测试过程可视化</h1>
        </div>
        <p className="app-subtitle">
          虚拟时间线 · 插话打断 · 快进压缩 · 重叠说话
        </p>
        <div className="header-actions">
          <button
            type="button"
            className="import-button"
            onClick={handleImportClick}
          >
            导入事件流 JSON
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json,.json"
            style={{ display: 'none' }}
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) handleImportFile(file)
              event.target.value = ''
            }}
          />
        </div>
      </header>
      <div
        className="app-stage"
        style={{ '--left-width': `${leftWidth}px` } as CSSProperties}
      >
        <RunConsole
          state={state}
          onSelect={(caseId) => dispatch({ type: 'selectCase', caseId })}
          onStart={handleStart}
          onStop={handleStop}
        />
        <ChatStream entries={entries} />
        <PanelResizer
          orientation="vertical"
          onResize={handleLeftResize}
          label="调整对话流与观察区宽度"
        />
        <div
          className="right-column"
          style={
            {
              '--timeline-h': `${timelineHeight}px`,
              '--car-h': `${carStateHeight}px`,
            } as CSSProperties
          }
        >
          <TimelineLanes
            scale={scale}
            spans={spans}
            overlaps={overlaps}
            toolSpans={toolSpans}
            liveSpans={liveSpans}
            playback={{
              active: playbackActive,
              mode: state.playback.mode,
              cursorMs: state.playback.cursorMs,
              speed: state.playback.speed,
            }}
            onScrub={handleScrub}
            onPlayPause={handlePlayPause}
            onSpeed={handleSpeed}
            view={replayView}
            onZoom={handleZoom}
            onPan={handlePan}
            onViewportWidth={handleViewportWidth}
          />
          <PanelResizer
            onResize={handleTimelineResize}
            label="调整时间线面板高度"
          />
          <CarStatePanel
            view={carView}
            cursorText={
              playbackActive
                ? `T+${formatDuration(state.playback.cursorMs)}`
                : nowMs !== null
                  ? `T+${formatDuration(nowMs)}`
                  : null
            }
            playing={state.playback.mode === 'playing'}
          />
          <PanelResizer
            onResize={handleCarStateResize}
            label="调整车态面板高度"
          />
          <VerdictPanel run={state.run} judge={state.judge} onJudge={handleJudge} />
        </div>
      </div>
    </main>
  )
}
