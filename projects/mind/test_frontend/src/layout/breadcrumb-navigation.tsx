import React, { useCallback, useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router'
import { Breadcrumb, type GetProp } from 'antd'
import { routes } from '@/routes/routes'
import { RollbackOutlined } from '@ant-design/icons'
import styles from './index.module.less'
import type { RouteItem } from '@/routes/routes'

type NavItemType = { path: string; name: string }

type BreadcrumbItemType = GetProp<typeof Breadcrumb, 'items'>[number] & {
  title: React.ReactNode
}

const getHomeItem = (isLegacy: boolean): BreadcrumbItemType => ({
  title: <Link to={isLegacy ? '/legacy' : '/'}>首页</Link>,
})

const matchRoutePath = function (route: string, path: string): boolean {
  const routeDirs = route.split('/')
  const pathDirs = path.split('/')
  if (routeDirs.length !== pathDirs.length) {
    return false
  }
  for (let i = 0; i < routeDirs.length; i++) {
    if (routeDirs[i].startsWith(':')) {
      continue
    }
    if (routeDirs[i] !== pathDirs[i]) {
      return false
    }
  }
  return true
}

const getBreadcrumbMap = (routes: RouteItem[], parentPath = ''): Record<string, string> => {
  const map: Record<string, string> = {}

  routes.forEach((route) => {
    const path = `${parentPath}/${route.path}`
    if (path) map[path] = route.name

    if (route.children) {
      Object.assign(map, getBreadcrumbMap(route.children, path))
    }
  })
  return map
}

const findMathRoute = function (path: string): NavItemType | undefined {
  const breadcrumbRouteMap = getBreadcrumbMap(routes)
  for (const route in breadcrumbRouteMap) {
    if (matchRoutePath(route, path)) {
      return { path: path, name: breadcrumbRouteMap[route] }
    }
  }
  return undefined
}

const BreadcrumbNavigation: React.FC = () => {
  const location = useLocation()
  const [breadcrumbItems, setBreadcrumbItems] = useState<BreadcrumbItemType[]>([getHomeItem(false)])
  const [backPath, setBackPath] = useState<string>('')

  const isLegacy = location.pathname.startsWith('/legacy')

  const initBreadcrumbItems = useCallback(() => {
    const rawPath = isLegacy ? location.pathname.replace(/^\/legacy/, '') : location.pathname
    const navItems: NavItemType[] = []
    let targetPath = rawPath.startsWith('/') ? rawPath : '/' + rawPath
    if (targetPath === '/') targetPath = ''
    let matchedRoute: NavItemType | undefined
    while (targetPath !== '') {
      matchedRoute = findMathRoute(targetPath)
      if (matchedRoute) {
        const legacyPath = isLegacy ? `/legacy${matchedRoute.path}` : matchedRoute.path
        navItems.unshift({ ...matchedRoute, path: legacyPath })
      }
      targetPath = targetPath.split('/').slice(0, -1).join('/')
    }
    const newBreadcrumbItems: BreadcrumbItemType[] = []
    newBreadcrumbItems.push(getHomeItem(isLegacy))
    navItems.map((item, index) => {
      if (index === navItems.length - 1 || index === 0) {
        newBreadcrumbItems.push({ title: item.name })
      } else {
        newBreadcrumbItems.push({
          title: <Link to={item.path}>{item.name}</Link>,
        })
      }
    })
    setBreadcrumbItems(newBreadcrumbItems)
    setBackPath(navItems.length > 2 ? navItems[navItems.length - 2].path : '')
  }, [setBreadcrumbItems, setBackPath, location.pathname, isLegacy])

  useEffect(() => {
    initBreadcrumbItems()
  }, [location, initBreadcrumbItems])

  return (
    <div className={styles.navigation}>
      <Breadcrumb items={breadcrumbItems} separator=">" className={styles.breadcrumb} />
      {!!backPath && window.history.length > 2 && (
        <a onClick={() => window.history.back()}>
          <RollbackOutlined /> 返回
        </a>
      )}
      {!!backPath && window.history.length < 2 && (
        <Link to={backPath}>
          <RollbackOutlined /> 返回
        </Link>
      )}
    </div>
  )
}

export default BreadcrumbNavigation
