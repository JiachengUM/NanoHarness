import React, { useEffect, useMemo } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router'
import { Avatar, Button, Dropdown, Layout, message, Space, Tag } from 'antd'
import type { MenuProps } from 'antd'
import { LoginOutlined, LogoutOutlined, UserOutlined, HistoryOutlined, RocketOutlined } from '@ant-design/icons'
import SvgIcon from '@/components/SvgIcon'
import styles from './index.module.less'
import SiderBar from './sider-bar'
import BreadcrumbNavigation from './breadcrumb-navigation'
import useSystemStore from '@/stores/system'
import Api from '@/apis/task-data'

const { Header, Content } = Layout
let messageShow = false

const App: React.FC = () => {
  const [messageApi, contextHolder] = message.useMessage()
  const { currentUser, setCurrentUser, clearCurrentUser } = useSystemStore()
  const location = useLocation()
  const navigate = useNavigate()

  const isLegacy = location.pathname.startsWith('/legacy')

  const toggleMode = () => {
    const currentPath = location.pathname
    const search = location.search
    if (isLegacy) {
      const newPath = currentPath.replace(/^\/legacy/, '') || '/'
      navigate(newPath + search)
    } else {
      navigate(`/legacy${currentPath}${search}`)
    }
  }

  const handleLogin = () => {
    const redirect = `${window.location.pathname}${window.location.search}`
    window.location.href = Api.auth.feishuLoginUrl(redirect)
  }

  const handleLogout = async () => {
    await Api.auth.logout()
    clearCurrentUser()
    messageApi.success('已退出登录')
  }

  useEffect(() => {
    Api.auth.me()
      .then((user) => {
        if (user) {
          setCurrentUser(user)
          return
        }
        clearCurrentUser()
        if (!messageShow) {
          messageShow = true
          messageApi.warning('请先飞书登录')
        }
      })
      .catch(() => {
        clearCurrentUser()
      })
  }, [clearCurrentUser, messageApi, setCurrentUser])

  const menuItems: MenuProps['items'] = [
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: handleLogout,
    },
  ]

  const modeTag = useMemo(() => {
    if (isLegacy) {
      return (
        <Tag color="orange" icon={<HistoryOutlined />} style={{ margin: 0, cursor: 'pointer' }} onClick={toggleMode}>
          老接口模式 - 点击切换新版
        </Tag>
      )
    }
    return (
      <Tag color="green" icon={<RocketOutlined />} style={{ margin: 0, cursor: 'pointer' }} onClick={toggleMode}>
        新接口模式 - 点击切换旧版
      </Tag>
    )
  }, [isLegacy])

  return (
    <>
      {contextHolder}
      <Layout className={styles.container}>
        <Header className={styles.header}>
          <div className={styles.title}>
            <SvgIcon className={styles.icon} name="logo" />
            <div>智能体演练场</div>
            {modeTag}
          </div>
          <Space size={16}>
            {currentUser ? (
              <Dropdown menu={{ items: menuItems }} placement="bottomRight">
                <Button icon={<Avatar size={20} src={currentUser.avatar_url} icon={<UserOutlined />} />}>
                  {currentUser.name}
                </Button>
              </Dropdown>
            ) : (
              <Button type="primary" icon={<LoginOutlined />} onClick={handleLogin}>
                飞书登录
              </Button>
            )}
          </Space>
        </Header>
        <Layout>
          <SiderBar />
          <Layout className={styles.contentLayout}>
            <BreadcrumbNavigation />
            <Content className={styles.content}>
              <Outlet />
            </Content>
          </Layout>
        </Layout>
      </Layout>
    </>
  )
}

export default App
