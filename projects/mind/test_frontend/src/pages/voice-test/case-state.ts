import { normalizeVoiceCaseForm, toVoiceCaseFormData } from './case-form'

function hasBlankUserContent(messages: Message[]): boolean {
  for (const msg of messages) {
    if ((msg.role || '').trim().toLowerCase() !== 'user') {
      continue
    }
    if (!(msg.content || '').trim()) {
      return true
    }
  }
  return false
}

function validateUserQueryListsStructure(lists: (Message[] | DialogueRoundConfig)[]): string | null {
  if (!lists.length) {
    return 'user_query_lists 至少需要一项会话'
  }

  for (let i = 0; i < lists.length; i += 1) {
    const session = lists[i]
    if (Array.isArray(session)) {
      if (session.length === 0) {
        return `user_query_lists[${i}] 不能为空，至少需要一条用户消息`
      }
      if (session.length > 1) {
        return `user_query_lists[${i}] 每组冷启动仅允许一条用户消息`
      }
      if (hasBlankUserContent(session)) {
        return `user_query_lists[${i}] 的用户消息 content 不能为空`
      }
    } else if (session && typeof session === 'object') {
      const userList = session.user_query_list || []
      if (userList.length === 0) {
        return `user_query_lists[${i}].user_query_list 不能为空，至少需要一条用户消息`
      }
      if (userList.length > 1) {
        return `user_query_lists[${i}].user_query_list 每组冷启动仅允许一条用户消息`
      }
      if (hasBlankUserContent(userList)) {
        return `user_query_lists[${i}].user_query_list 的用户消息 content 不能为空`
      }
    } else {
      return `user_query_lists[${i}] 格式无效`
    }
  }

  return null
}

export function validateVoiceCase(form: ComplexReasoningCase): string | null {
  const normalized = normalizeVoiceCaseForm(toVoiceCaseFormData(form))

  const listsError = validateUserQueryListsStructure(normalized.user_query_lists || [])
  if (listsError) {
    return listsError
  }

  const assertions = (normalized.nl_assertion || []).filter((s) => (s || '').trim())
  if (assertions.length === 0) {
    return '请填写至少一条自然语言断言'
  }

  if (!normalized.max_round || normalized.max_round < 1) {
    return '最大对话轮数至少为 1'
  }

  if (!normalized.case_id?.trim()) {
    return 'case_id 不能为空'
  }

  if (normalized.context_config !== undefined && normalized.context_config !== null) {
    if (typeof normalized.context_config !== 'object' || Array.isArray(normalized.context_config)) {
      return 'context_config 须为 JSON 对象'
    }
  }

  if (normalized.code_assertion !== undefined && normalized.code_assertion !== null) {
    if (typeof normalized.code_assertion !== 'object' || Array.isArray(normalized.code_assertion)) {
      return 'code_assertion 须为 JSON 对象'
    }
  }

  return null
}
