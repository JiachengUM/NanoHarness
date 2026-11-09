import { AGENT_ARENA_BASE_URL } from '@/request/https'
import { message } from 'antd'
import useApiModeStore from '@/stores/apiMode'

const API_PREFIX = AGENT_ARENA_BASE_URL

// GET Api 导出数据
export function exportJsonGet(url: string, params: Record<string, string>, fileName: string = '导出数据.json') {
  const ext = fileName.split('.').pop() || 'json'
  exportFileGet(url, params, fileName, `.${ext}`)
}

export function exportExcelGet(url: string, params: Record<string, string> = {}, fileName: string = '导出数据.xlsx') {
  exportFileGet(url, params, fileName, '.xlsx')
}

function exportFileGet(url: string, params: Record<string, string>, fileName: string, extension: string) {
  const paramsStr = new URLSearchParams(params)
  if (!url.startsWith(API_PREFIX)) url = API_PREFIX + url
  const resolveFullUrl = useApiModeStore.getState().resolveFullUrl
  url = resolveFullUrl(url, API_PREFIX)
  const _url = `${url}?${paramsStr.toString()}`

  message.info('数据导出中，请稍后...')

  fetch(_url, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/octet-stream',
    },
  })
    .then((res) => {
      if (!res.ok) {
        message.error('导出失败！')
        return
      } else {
        return res.blob()
      }
    })
    .then((blob) => {
      if (!blob) return

      if (fileName.indexOf(extension) === -1) {
        fileName = fileName + extension
      }

      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = fileName
      a.click()
      window.URL.revokeObjectURL(url)
    })
}
