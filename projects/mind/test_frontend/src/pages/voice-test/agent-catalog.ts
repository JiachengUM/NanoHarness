import { get, BASE_URL } from '@/request/https'

export type VoiceTestAgentOption = {
  value: string
  label: string
  description: string
  test_mode: 'voice' | 'text'
}

export const VOICE_TEST_TARGET_VOICE = 'voice'
export const VOICE_TEST_TARGET_AGENT_V1 = 'AgentV1'

/** API 不可用时仅保留语音链路，避免页面不可用 */
export const VOICE_ONLY_FALLBACK: VoiceTestAgentOption[] = [
  {
    value: VOICE_TEST_TARGET_VOICE,
    label: '语音链路',
    description: '浏览器麦克风收音 + TTS 播报',
    test_mode: 'voice',
  },
]

export function fetchVoiceAgentOptions() {
  return get<VoiceTestAgentOption[]>(`${BASE_URL}/voice_test/agent_options`)
}

export function isVoiceTarget(target: string): boolean {
  return target === VOICE_TEST_TARGET_VOICE
}

export function agentOptionLabel(options: VoiceTestAgentOption[], target: string): string {
  return options.find((item) => item.value === target)?.label ?? target
}
