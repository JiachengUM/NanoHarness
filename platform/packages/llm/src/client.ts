import OpenAI, { ClientOptions } from 'openai'
import { CREDENTIALS } from './constants/credentials'

export function createClient(options?: ClientOptions): OpenAI {
  // 创建OpenAI客户端实例

  return new OpenAI({
    baseURL: CREDENTIALS.ARK_BASE_URL,
    apiKey: CREDENTIALS.ARK_API_KEY,
    ...options,
  })
}
