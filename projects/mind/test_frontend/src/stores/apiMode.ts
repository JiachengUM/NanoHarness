import { create } from 'zustand'

type ApiMode = 'new' | 'legacy'

interface ApiModeStore {
  mode: ApiMode
  setMode: (mode: ApiMode) => void
  resolveUrl: (basePath: string) => string
  resolvePath: (path: string) => string
  resolveFullUrl: (fullUrl: string, baseUrl: string) => string
}

const useApiModeStore = create<ApiModeStore>((set, get) => ({
  mode: 'new',
  setMode: (mode: ApiMode) => set({ mode }),
  resolveUrl: (basePath: string) => {
    const { mode } = get()
    if (mode !== 'legacy') return basePath
    return `/legacy${basePath}`
  },
  resolvePath: (path: string) => {
    const { mode } = get()
    if (mode !== 'legacy') return path
    if (!path.startsWith('/')) return path
    if (path.startsWith('/legacy')) return path
    return `/legacy${path}`
  },
  resolveFullUrl: (fullUrl: string, baseUrl: string) => {
    const { mode } = get()
    if (mode !== 'legacy') return fullUrl
    if (fullUrl.startsWith('/legacy')) return fullUrl
    if (fullUrl.startsWith('/')) {
      return `/legacy${fullUrl}`
    }
    if (baseUrl.startsWith('http') && fullUrl.startsWith(baseUrl)) {
      const rest = fullUrl.slice(baseUrl.length)
      const baseOrigin = baseUrl.split('/').slice(0, 3).join('/')
      return `${baseOrigin}/legacy${rest}`
    }
    return fullUrl
  },
}))

export default useApiModeStore
