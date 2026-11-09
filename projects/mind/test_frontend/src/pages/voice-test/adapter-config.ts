import { get, BASE_URL } from '@/request/https'
import type { FrontendVadConfig } from './audio-helper'

/** 与 projects/voice_test/core/config.py Speaker 取值一致 */
export const S2S_SPEAKER_OPTIONS = [
  {
    label: 'vv · 活泼灵动女声',
    value: 'zh_female_vv_jupiter_bigtts',
  },
  {
    label: 'xiaohe · 甜美台湾口音女声',
    value: 'zh_female_xiaohe_jupiter_bigtts',
  },
  {
    label: 'yunzhou · 清爽沉稳男声',
    value: 'zh_male_yunzhou_jupiter_bigtts',
  },
  {
    label: 'xiaotian · 清爽磁性男声',
    value: 'zh_male_xiaotian_jupiter_bigtts',
  },
] as const

export type S2sSpeaker = (typeof S2S_SPEAKER_OPTIONS)[number]['value']

/** 与 projects/voice_test/adapter/config.py VoiceAdapterConfig 字段一致 */
export type VoiceAdapterConfig = {
  wake_up_word: string
  goodbye_markers: string[]
  goodbye_reply: string
  vad_timeout_ms: number
  external_reply_timeout_sec: number
  log_asr_events: boolean
  log_asr_delta: boolean
  session_id_prefix: string
  memory_extraction_wait_sec: number
  run_gap_wait_sec: number
  /** S2S 假人播报音色；与页面回放 HTTP TTS 的 male/female 无关 */
  s2s_speaker: S2sSpeaker
  /** 定制化：唤醒词与首句拆分发送（两次 SayHello，中间等待） */
  split_wake_up_and_first_query: boolean
  /** 拆分发送时唤醒词与首句之间的等待（ms） */
  split_wake_up_wait_ms: number
  // ---------------------------------------------------------------------------
  // 前端 Silero VAD 参数（仅浏览器端生效，后端 pydantic 忽略未知字段，不会 422）
  // ---------------------------------------------------------------------------
  /** 前端 VAD 开关：true=Silero VAD 段式发送；false=流式 200ms 帧发送（后端缓存节流） */
  frontend_vad_enabled: boolean
  /** 最短语音段（ms）：低于此长度的语音视为噪声丢弃（misfire）。小=更敏感，能抓快速短回复 */
  vad_min_speech_ms: number
  /** pre pending：语音开始前补的前导静音（ms），防吞字头 */
  vad_pre_speech_pad_ms: number
  /** post pending/静音判停：语音结束后等多久静音才切句（ms）。大=切句更稳，防句中被切断 */
  vad_redemption_ms: number
  /** 语音开始判定阈值（0~1）：高=更难触发，滤噪声；低=更灵敏 */
  vad_positive_threshold: number
  /** 语音结束判定阈值（0~1）：低=更难判定结束，段更完整 */
  vad_negative_threshold: number
}

export const VOICE_ADAPTER_CONFIG_STORAGE_KEY = 'voice-adapter-config'

export const FALLBACK_ADAPTER_CONFIG: VoiceAdapterConfig = {
  wake_up_word: '你好奔驰。',
  goodbye_markers: ['退下'],
  goodbye_reply: '（助手已结束会话）',
  vad_timeout_ms: 3000,
  external_reply_timeout_sec: 15,
  log_asr_events: true,
  log_asr_delta: true,
  session_id_prefix: 'voice-test',
  memory_extraction_wait_sec: 10,
  run_gap_wait_sec: 1,
  s2s_speaker: 'zh_female_vv_jupiter_bigtts',
  split_wake_up_and_first_query: false,
  split_wake_up_wait_ms: 3000,
  // 前端 VAD 默认值：与 audio-helper DEFAULT_VAD_CONFIG 对齐（表单重置时用同一套）
  frontend_vad_enabled: false,
  vad_min_speech_ms: 300,
  vad_pre_speech_pad_ms: 1500,
  vad_redemption_ms: 1500,
  vad_positive_threshold: 0.5,
  vad_negative_threshold: 0.15,
}

/** 从 VoiceAdapterConfig 提取前端 VAD 参数（供 BrowserVoiceAudio 初始化） */
export function frontendVadFromConfig(config: VoiceAdapterConfig): FrontendVadConfig {
  return {
    min_speech_ms: config.vad_min_speech_ms,
    pre_speech_pad_ms: config.vad_pre_speech_pad_ms,
    redemption_ms: config.vad_redemption_ms,
    positive_threshold: config.vad_positive_threshold,
    negative_threshold: config.vad_negative_threshold,
  }
}

export function loadStoredAdapterConfig(): VoiceAdapterConfig {
  const raw = localStorage.getItem(VOICE_ADAPTER_CONFIG_STORAGE_KEY)
  if (!raw) {
    return { ...FALLBACK_ADAPTER_CONFIG }
  }
  try {
    const parsed = JSON.parse(raw) as Partial<VoiceAdapterConfig>
    return { ...FALLBACK_ADAPTER_CONFIG, ...parsed }
  } catch {
    return { ...FALLBACK_ADAPTER_CONFIG }
  }
}

export function saveAdapterConfig(config: VoiceAdapterConfig): void {
  localStorage.setItem(VOICE_ADAPTER_CONFIG_STORAGE_KEY, JSON.stringify(config))
}

export function parseGoodbyeMarkers(text: string): string[] {
  return text
    .split(/[,，]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

export function formatGoodbyeMarkers(markers: string[]): string {
  return markers.join('，')
}

export function fetchAdapterConfig() {
  return get<VoiceAdapterConfig>(`${BASE_URL}/voice_test/adapter_config`)
}

/** PAUSED 状态的 task_run 列表项（与后端 GET /paused_runs 对齐） */
export type PausedRunItem = {
  task_run_id: string
  task_id: string | null
  progress?: { completed?: number; total?: number } | null
  metadata?: Record<string, unknown> | null
  updated_time?: string | null
}

/** 查询最近 PAUSED 状态的 voice 测试 task_run（最多 10 条，按更新时间倒序） */
export function fetchPausedRuns() {
  return get<PausedRunItem[]>(`${BASE_URL}/voice_test/paused_runs`)
}

/** 单个 task_run 的状态查询结果（与后端 GET /task_run/{id} 对齐） */
export type TaskRunStatusInfo = {
  task_run_id: string
  status: string
  progress?: { completed?: number; total?: number } | null
  metadata?: Record<string, unknown> | null
  updated_time?: string | null
  /** 后端校验：status=PAUSED 且 metadata 含 dataset_id 才可续跑 */
  resumable?: boolean
}

/**
 * 查询单个 task_run 状态，供恢复前校验。
 * - 200 返回状态信息，前端按 status 判断是否继续恢复
 * - 404 / 网络错误返回 null，前端按"不可恢复"处理
 */
export async function fetchTaskRunStatus(taskRunId: string): Promise<TaskRunStatusInfo | null> {
  try {
    return await get<TaskRunStatusInfo>(`${BASE_URL}/voice_test/task_run/${taskRunId}`)
  } catch {
    return null
  }
}
