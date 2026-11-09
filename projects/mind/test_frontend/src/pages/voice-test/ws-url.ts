/** 语音测试 WebSocket：优先显式配置，其次直连 API 基址，最后走当前站点 /api 代理。 */
export function getVoiceTestWsUrl(isLegacy = false): string {
  const explicit = import.meta.env.VITE_VOICE_TEST_WS_URL as string | undefined
  if (explicit) {
    return explicit
  }

  const legacyApiBase = import.meta.env.VITE_LEGACY_DEFAULT_API_URL as string | undefined
  const apiBase = import.meta.env.VITE_DEFAULT_API_URL as string | undefined
  if (isLegacy && legacyApiBase && legacyApiBase.startsWith('http')) {
    return `${legacyApiBase.replace(/^http/, 'ws').replace(/\/$/, '')}/voice_test/session`
  }
  if (apiBase && apiBase.startsWith('http')) {
    return `${apiBase.replace(/^http/, 'ws').replace(/\/$/, '')}/voice_test/session`
  }

  const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const path = isLegacy ? '/legacy/api/voice_test/session' : '/api/voice_test/session'
  return `${wsProto}//${window.location.host}${path}`
}
