import React, { useEffect, useState } from 'react'
import { BrowserRouter } from 'react-router'
import { message, ConfigProvider } from 'antd'
import '@ant-design/v5-patch-for-react-19'
import { ErrorBoundary } from 'react-error-boundary'
import zhCN from 'antd/locale/zh_CN'
import Routes from './routes'
import Error500 from '@/pages/error/500'
import { MessageContext } from './context/messageContext'
import { GenerationProvider } from './context/generationContext'

const CHUNK_ERROR_KEYWORDS = [
  'Failed to fetch dynamically imported module',
  'Loading chunk',
  'error loading dynamically imported module',
]

const isChunkLoadError = (error: Error): boolean => {
  const message = error?.message || ''
  return CHUNK_ERROR_KEYWORDS.some((keyword) => message.includes(keyword))
}

const handleChunkLoadError = () => {
  if (window.sessionStorage.getItem('chunk_reload_triggered')) {
    return
  }
  window.sessionStorage.setItem('chunk_reload_triggered', 'true')
  window.location.reload()
}

const App: React.FC = () => {
  const [messageApi, contextHolder] = message.useMessage()
  const [errorBoundaryKey, setErrorBoundaryKey] = useState(0)

  useEffect(() => {
    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason
      if (reason instanceof Error && isChunkLoadError(reason)) {
        event.preventDefault()
        handleChunkLoadError()
      }
    }

    window.addEventListener('unhandledrejection', handleUnhandledRejection)
    return () => {
      window.removeEventListener('unhandledrejection', handleUnhandledRejection)
    }
  }, [])

  const handleErrorBoundaryError = (error: Error) => {
    if (isChunkLoadError(error)) {
      handleChunkLoadError()
    }
  }

  const handleErrorBoundaryReset = () => {
    setErrorBoundaryKey((prev) => prev + 2)
  }

  return (
    <>
      {contextHolder}
      <React.Suspense>
        <ConfigProvider locale={zhCN}>
          <MessageContext.Provider value={messageApi}>
            <ErrorBoundary
              key={errorBoundaryKey}
              fallback={<Error500 />}
              onError={handleErrorBoundaryError}
              onReset={handleErrorBoundaryReset}
            >
              <GenerationProvider>
                <BrowserRouter>
                  <Routes />
                </BrowserRouter>
              </GenerationProvider>
            </ErrorBoundary>
          </MessageContext.Provider>
        </ConfigProvider>
      </React.Suspense>
    </>
  )
}

export default App
