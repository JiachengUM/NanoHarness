import axios from 'axios'
import type { AxiosInstance, AxiosResponse, AxiosRequestConfig } from 'axios'
import { message, notification } from 'antd'
import useSystemStore from '@/stores/system'
import useApiModeStore from '@/stores/apiMode'

export const BASE_URL = '/api'
export const ADVISOR_BASE_URL = '/v1'
export const AGENT_ARENA_BASE_URL = '/agent-arena-api'

const LEGACY_PREFIX = '/legacy'

const isLegacyBaseUrl = (url: string): boolean => {
  return url.startsWith(BASE_URL) || url.startsWith(ADVISOR_BASE_URL) || url.startsWith(AGENT_ARENA_BASE_URL)
}

const resolveLegacyUrl = (url: string): string => {
  const { mode } = useApiModeStore.getState()
  if (mode !== 'legacy') return url
  if (!isLegacyBaseUrl(url)) return url
  return `${LEGACY_PREFIX}${url}`
}

const resPromiseCache = new Map<string, Promise<unknown>>()

const http: AxiosInstance = axios.create({
  timeout: 60000,
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.request.use(
  (config) => {
    if (config.url) {
      config.url = resolveLegacyUrl(config.url)
    }
    if (config.params) config.params = deleteNullParams(config.params)
    if (config.data) config.data = deleteNullParams(config.data)

    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

http.interceptors.response.use(
  <T>(response: AxiosResponse<ApiRes<T>>) => {
    const { code, data, message } = response.data

    if (code >= 300) {
      showNotify(message)
      return Promise.reject(message)
    }

    return data
  },
  async (error) => {
    const data = error.response?.data
    let message = data?.message || error.message
    if (data.detail?.length) {
      message += `: ${data.detail
        .filter((item: any) => item.msg)
        .map((item: any) => item.msg)
        .join(', ')}`
    }
    showNotify(message)
    return Promise.reject(message)
  }
)

const cachedRequest = <T>(config: AxiosRequestConfig) => {
  const key = getUniKey(config)

  if (resPromiseCache.has(key)) return resPromiseCache.get(key) as Promise<T>

  const promise = http.request<T>(config)
  resPromiseCache.set(key, promise)
  promise.finally(() => resPromiseCache.delete(key))
  return promise as Promise<T>
}

const showNotify = (description = '服务端错误！', message = '请求出错！') => {
  notification.error({
    message,
    description,
  })
}

export default http

export const get = <T>(url: string, params?: object): Promise<T> => {
  return cachedRequest<T>({ method: 'get', url, params })
}

export const post = <T>(url: string, data: object = {}, needCreator = true): Promise<T> => {
  if (needCreator) {
    // 添加creator字段（主要是创建接口)
    const creator = useSystemStore.getState().username
    if (!creator) {
      message.error('请先飞书登录')
      return Promise.reject('请先飞书登录')
    }
    if (data) {
      ;(data as Common).creator = creator
    }
  }

  return cachedRequest<T>({ method: 'post', url, data })
}

export const put = <T>(url: string, data?: object): Promise<T> => {
  return cachedRequest<T>({ method: 'put', url, data })
}

export const del = <T>(url: string, params?: object, data?: object): Promise<T> => {
  return cachedRequest<T>({ method: 'delete', url, params, data })
}

export function deleteNullParams(params: { [key: string]: unknown }) {
  for (const key in params) {
    if (params[key] === null || params[key] === undefined || params[key] === '') {
      delete params[key]
    }
  }
  return params
}

function getUniKey(config: AxiosRequestConfig): string {
  const { method, url, params, data } = config
  return `${method}-${url}-${JSON.stringify(params)}-${JSON.stringify(data)}`
}
