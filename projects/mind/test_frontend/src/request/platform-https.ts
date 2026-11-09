import axios from 'axios'
import type { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios'
import { message, notification } from 'antd'
import { fetchEventSource } from '@microsoft/fetch-event-source'
import useSystemStore from '@/stores/system'
import useApiModeStore from '@/stores/apiMode'
import { deleteNullParams } from './https'

export const PLATFORM_BASE_URL = '/platform-api'

const LEGACY_PREFIX = '/legacy'

const resolveLegacyUrl = (url: string): string => {
  const { mode } = useApiModeStore.getState()
  if (mode !== 'legacy') return url
  if (!url.startsWith(PLATFORM_BASE_URL)) return url
  return `${LEGACY_PREFIX}${url}`
}

const requestCache = new Map<string, Promise<unknown>>()

const http: AxiosInstance = axios.create({
  timeout: 10 * 60 * 1000,
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.request.use((config) => {
  if (config.url) {
    config.url = resolveLegacyUrl(config.url)
  }
  if (config.params) config.params = deleteNullParams(config.params)
  if (config.data) config.data = deleteNullParams(config.data)
  return config
})

http.interceptors.response.use(
  <T>(response: AxiosResponse<ApiRes<T>>) => {
    const { code, data, message: responseMessage } = response.data
    if (code >= 300) {
      notification.error({ message: '请求出错', description: responseMessage })
      return Promise.reject(responseMessage)
    }
    return data
  },
  (error) => {
    const description = error.response?.data?.message || error.message || 'Platform 服务请求失败'
    notification.error({ message: '请求出错', description })
    return Promise.reject(error)
  }
)

function cachedRequest<T>(config: AxiosRequestConfig): Promise<T> {
  const key = `${config.method}-${config.url}-${JSON.stringify(config.params)}-${JSON.stringify(config.data)}`
  if (requestCache.has(key)) return requestCache.get(key) as Promise<T>

  const promise = http.request<T>(config)
  requestCache.set(key, promise)
  promise.finally(() => requestCache.delete(key))
  return promise as Promise<T>
}

export const platformGet = <T>(url: string, params?: object) =>
  cachedRequest<T>({ method: 'get', url, params })

export const platformPost = <T>(url: string, data: object = {}, needCreator = true) => {
  if (needCreator) {
    const creator = useSystemStore.getState().username
    if (!creator) {
      message.error('请先飞书登录')
      return Promise.reject(new Error('请先飞书登录'))
    }
    ;(data as Common).creator = creator
  }
  return cachedRequest<T>({ method: 'post', url, data })
}

export const platformPut = <T>(url: string, data?: object) =>
  cachedRequest<T>({ method: 'put', url, data })

export const platformDelete = <T>(url: string, params?: object) =>
  cachedRequest<T>({ method: 'delete', url, params })

export type PlatformSSEEvent<T = unknown> = {
  type: string
  data: T
}

export const platformPostSSE = async <T = unknown>(
  url: string,
  data: object,
  onEvent: (event: PlatformSSEEvent<T>) => void,
  onClose?: () => void,
  signal?: AbortSignal
) => fetchEventSource(resolveLegacyUrl(url), {
  method: 'POST',
  openWhenHidden: true,
  signal,
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify(data),
  async onopen(response) {
    if (!response.ok) {
      throw new Error(`Platform SSE 请求失败：${response.status}`)
    }
  },
  onmessage(event) {
    if (!event.data) return
    onEvent(JSON.parse(event.data) as PlatformSSEEvent<T>)
  },
  onclose() {
    onClose?.()
  },
})
