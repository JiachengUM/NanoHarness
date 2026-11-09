import { fetchEventSource } from '@microsoft/fetch-event-source'
import { BASE_URL } from '@/request/https'
import useSystemStore from '@/stores/system'
import useApiModeStore from '@/stores/apiMode'

export type SSERES<T> = {
  code: number
  msg: string
  result: T
}

const resolveLegacyUrl = (url: string): string => {
  const { mode } = useApiModeStore.getState()
  if (mode !== 'legacy') return url
  return `/legacy${url}`
}

const sseRequest = async <P, T>(
  url: string,
  method: string,
  data: P,
  onMessage: (data: T) => void,
  onClose: () => void
) => {
  const fullUrl = resolveLegacyUrl(BASE_URL + url)

  const _data = { ...data, creator: useSystemStore.getState().username } // 添加 creator 字段

  return await fetchEventSource(fullUrl, {
    method,
    openWhenHidden: true,
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(_data),
    async onopen() {},
    onmessage(ev) {
      try {
        const data = JSON.parse(ev.data) as SSERES<T>
        if (data) onMessage?.(data.result || (data as T))
      } catch (e) {
        console.log(e)
      }
    },
    onerror(err) {
      console.log('SSE error:', err)
      throw err
    },
    onclose() {
      onClose?.()
    },
  })
}

export default sseRequest
