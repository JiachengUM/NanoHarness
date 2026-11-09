import { useRoutes } from 'react-router'
import type { RouteObject } from 'react-router'
import { useEffect } from 'react'
import { useLocation } from 'react-router'
import Layout from '@/layout'
import useApiModeStore from '@/stores/apiMode'
import { pages, routes, type RouteItem } from './routes'

function getRoutes(routes: RouteItem[]): RouteObject[] {
  return routes.map((route) => {
    return {
      path: route.path,
      element: route.element,
      index: route.index,
      children: route.children ? getRoutes(route.children) : undefined,
    }
  })
}

function ApiModeSync() {
  const location = useLocation()
  const setMode = useApiModeStore((s) => s.setMode)

  useEffect(() => {
    const isLegacy = location.pathname.startsWith('/legacy')
    setMode(isLegacy ? 'legacy' : 'new')
  }, [location.pathname, setMode])

  return null
}

const getAppRoutes = (): RouteObject[] => {
  const mainRoutes = getRoutes(routes)

  return [
    {
      element: (
        <>
          <ApiModeSync />
          <Layout />
        </>
      ),
      children: [...mainRoutes],
    },
    {
      path: 'legacy',
      element: (
        <>
          <ApiModeSync />
          <Layout />
        </>
      ),
      children: [...mainRoutes],
    },
    {
      path: '403',
      Component: pages.Error403,
    },
    {
      path: '*',
      Component: pages.Error404,
    },
  ]
}

export default function Routes() {
  return useRoutes(getAppRoutes())
}
