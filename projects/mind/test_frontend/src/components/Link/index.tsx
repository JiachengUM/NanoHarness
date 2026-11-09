import React from 'react'
import { LoadingOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router'

type Props = {
  link?: string
  blank?: boolean // 是否新窗口打开
  loading?: boolean // 是否显示加载中
  disabled?: boolean // 是否禁用
  onClick?: () => void
  children?: React.ReactNode
}

const Link: React.FC<Props> = (props) => {
  const { link, blank = false, disabled = false, loading = false, onClick, children } = props
  const navigate = useNavigate()

  const toLink = () => {
    if (disabled || loading) return

    if (onClick) return onClick()

    if (!link) return

    if (blank) return window.open(link, '_blank')

    navigate(link)
  }

  return (
    <a className={`${disabled ? 'disabled' : ''}`} onClick={toLink}>
      {loading ? <LoadingOutlined /> : children}
    </a>
  )
}

export default Link
