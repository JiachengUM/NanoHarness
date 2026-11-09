/** 本地记录服务 HTTP 客户端：只传 batch_id / case_id，目录怎么建由本地记录服务决定。 */

import { BASE_URL } from '@/request/https'

export const LOCAL_RECORDER_DOWNLOAD_URL = `${BASE_URL}/voice_test/local_recorder/download`

export type LocalRecorderConfig = {
  enabled: boolean
  baseUrl: string
  /** 本批文件夹名，原样传给本地记录服务 */
  batchId: string
}

export type LocalRecorderHealth = {
  ready: boolean
  devices: string[]
  recording: string | null
  output_dir: string
  issues: string[]
  tos_enabled?: boolean
}

export type LocalRecorderStopItem = {
  ok: boolean
  case_id: string
  dir: string
  message: string
}

export type LocalRecorderCaseResult = {
  ok: boolean
  case_id: string
  dir: string
  result_tag: 'PASS' | 'FAIL' | 'SKIP' | 'ERROR'
  message: string
}

export type LocalRecorderCaseResultPayload = {
  case_id: string
  /** /start 返回的录制目录绝对路径，后端直接用它写结果，不再反查 */
  dir: string
  execution_success?: boolean
  execution_error?: string | null
  judge_status?: 'completed' | 'skipped' | 'failed' | 'not_run'
  is_passed?: boolean | null
  reason?: string | null
  repeat_index?: number | null
  repeat_n?: number | null
  history_for_judge?: string
  /** TOS 上传：task_run_item_id 非空时后端会启动后台上传 merged.mp4 */
  task_run_item_id?: string
  /** TOS 上传完成后回调后端更新 metadata 的 URL */
  callback_url?: string
  /** 与 /start 一致：repeat_n>1 才传，否则 0；透传写入 case_result.json */
  run_index?: number
}

const STORAGE_KEY = 'voice-local-recorder-config'
const LEGACY_STORAGE_KEYS = ['voice-sidecar-config', 'voice-sidecar-url']

export const DEFAULT_LOCAL_RECORDER_URL = 'http://127.0.0.1:8765'

export const DEFAULT_LOCAL_RECORDER_CONFIG: LocalRecorderConfig = {
  enabled: true,
  baseUrl: DEFAULT_LOCAL_RECORDER_URL,
  batchId: '',
}

function readStoredConfigRaw(): string | null {
  const current = localStorage.getItem(STORAGE_KEY)
  if (current) {
    return current
  }
  for (const key of LEGACY_STORAGE_KEYS) {
    const legacy = localStorage.getItem(key)
    if (legacy) {
      return legacy
    }
  }
  return null
}

export function loadLocalRecorderConfig(): LocalRecorderConfig {
  const raw = readStoredConfigRaw()
  if (!raw) {
    return { ...DEFAULT_LOCAL_RECORDER_CONFIG }
  }
  try {
    const parsed = JSON.parse(raw) as Partial<LocalRecorderConfig & { batchName?: string }>
    const batchId =
      typeof parsed.batchId === 'string'
        ? parsed.batchId
        : typeof parsed.batchName === 'string'
          ? parsed.batchName
          : ''
    return {
      ...DEFAULT_LOCAL_RECORDER_CONFIG,
      baseUrl: (parsed.baseUrl || '').trim() || DEFAULT_LOCAL_RECORDER_URL,
      batchId,
      enabled: parsed.enabled === true,
    }
  } catch {
    if (raw.startsWith('http')) {
      return { ...DEFAULT_LOCAL_RECORDER_CONFIG, baseUrl: raw }
    }
  }
  return { ...DEFAULT_LOCAL_RECORDER_CONFIG }
}

export function saveLocalRecorderConfig(config: LocalRecorderConfig): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config))
}

export function localRecorderConfigured(config: LocalRecorderConfig): boolean {
  return config.enabled && !!config.baseUrl.trim()
}

/** 仅语音通道且开关开启时才会真正开/停本地记录 */
export function localRecorderShouldRun(
  config: LocalRecorderConfig,
  isVoiceChannel: boolean,
): boolean {
  return isVoiceChannel && localRecorderConfigured(config)
}

export function describeLocalRecorderHealth(health: LocalRecorderHealth | null): {
  connected: boolean
  ready: boolean
  text: string
} {
  if (!health) {
    return {
      connected: false,
      ready: false,
      text: '连不上本地记录服务，请确认本地记录工具已启动',
    }
  }
  if (health.issues.length > 0) {
    return { connected: true, ready: false, text: health.issues.join(' · ') }
  }
  const dev = health.devices.length ? health.devices.join('、') : '未知'
  return {
    connected: true,
    ready: true,
    text: `设备已连接（${dev}）`,
  }
}

async function fetchJson<T>(baseUrl: string, path: string, init?: RequestInit): Promise<T> {
  const url = `${baseUrl.replace(/\/$/, '')}${path}`
  const response = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  })
  const data = (await response.json().catch(() => ({}))) as T & { detail?: string }
  if (!response.ok) {
    throw new Error(typeof data.detail === 'string' ? data.detail : `HTTP ${response.status}`)
  }
  return data
}

export async function fetchLocalRecorderHealth(baseUrl: string): Promise<LocalRecorderHealth | null> {
  if (!baseUrl.trim()) {
    return null
  }
  try {
    return await fetchJson<LocalRecorderHealth>(baseUrl, '/health')
  } catch {
    return null
  }
}

export async function localRecorderStart(
  config: LocalRecorderConfig,
  caseId: string,
  runIndex = 0,
): Promise<{ dir: string } | null> {
  if (!localRecorderConfigured(config) || !caseId.trim()) {
    return null
  }
  try {
    return await fetchJson<{ dir: string }>(config.baseUrl, '/start', {
      method: 'POST',
      body: JSON.stringify({
        case_id: caseId,
        batch_id: config.batchId,
        run_index: runIndex > 0 ? runIndex : 0,
      }),
    })
  } catch {
    return null
  }
}

export async function localRecorderStop(
  config: LocalRecorderConfig,
  caseId = '',
): Promise<LocalRecorderStopItem[]> {
  if (!localRecorderConfigured(config)) {
    return []
  }
  try {
    const body: { case_id?: string } = {}
    if (caseId.trim()) {
      body.case_id = caseId
    }
    const data = await fetchJson<{ stopped: LocalRecorderStopItem[] }>(config.baseUrl, '/stop', {
      method: 'POST',
      body: JSON.stringify(body),
    })
    return data.stopped || []
  } catch {
    return []
  }
}

export async function localRecorderWriteCaseResult(
  config: LocalRecorderConfig,
  payload: LocalRecorderCaseResultPayload,
): Promise<LocalRecorderCaseResult | null> {
  if (!localRecorderConfigured(config) || !payload.case_id.trim()) {
    return null
  }
  try {
    return await fetchJson<LocalRecorderCaseResult>(config.baseUrl, '/case_result', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  } catch {
    return null
  }
}
