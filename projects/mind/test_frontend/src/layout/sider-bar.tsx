import { Layout, Menu, theme } from 'antd'
import type { MenuProps } from 'antd'
import React, { useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons'
import { routes } from '@/routes/routes'
import type { RouteItem } from '@/routes/routes'
import styles from './index.module.less'

type MenuItem = Required<MenuProps>['items'][number]

const { useToken } = theme

const getMenus = (routes: RouteItem[], parentPath = ''): MenuItem[] => {
  return routes
    .filter((route) => {
      if (route.hiddenInMenu) return false
      return true
    })
    .map((route) => {
      const pathKey = `${parentPath}/${route.path}`

      return {
        key: pathKey,
        label: route.name,
        icon: route.icon,
        children: route.children ? getMenus(route.children, pathKey) : undefined,
      }
    })
}

const Sider: React.FC = () => {
  const location = useLocation()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)
  const { token } = useToken()

  const isLegacy = location.pathname.startsWith('/legacy')

  const menuItems = useMemo(() => {
    return getMenus(routes)
  }, [])

  const menuClick: MenuProps['onClick'] = (e) => {
    const targetPath = isLegacy ? `/legacy${e.key}` : e.key
    if (targetPath === location.pathname) return

    navigate(targetPath)
  }

  return (
    <Layout.Sider
      width={200}
      collapsible
      theme="light"
      collapsed={collapsed}
      style={{ overflow: 'auto', marginBottom: 48 }}
      onCollapse={(value) => setCollapsed(value)}
      trigger={
        <div className={styles.trigger} style={{ color: token.colorPrimary }}>
          {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
        </div>
      }
    >
      <Menu
        className={styles.menu}
        mode="inline"
        selectedKeys={[isLegacy ? location.pathname.replace(/^\/legacy/, '') : location.pathname]}
        items={menuItems}
        onClick={menuClick}
      />
    </Layout.Sider>
  )
}

export default Sider
