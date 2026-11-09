import React, { useContext, useMemo } from 'react'
import { Popconfirm, theme } from 'antd'
import { QuestionCircleOutlined } from '@ant-design/icons'
import { MessageContext } from '@/context/messageContext'

const { useToken } = theme

type Props<T> = {
  id?: T
  onDelete?: () => void
  disabled?: boolean
  API?: (id: T) => Promise<void>
  children?: React.ReactNode
  onSuccess?: () => void
  desc?: React.ReactNode
}

const ExDeleteButton = <T extends string | number = string>(props: Props<T>) => {
  const { API, id, onDelete } = props
  const { token } = useToken()
  const messageApi = useContext(MessageContext)

  const disabled = useMemo(() => {
    if (props.disabled) return true

    return false
  }, [props.disabled])

  const handleDelete = () => {
    onDelete?.()

    if (!id || !API) return

    API?.(id).then(() => {
      messageApi.success({ content: '删除成功' })
      props.onSuccess?.()
    })
  }

  return (
    <Popconfirm
      title="删除提示"
      description={props.desc || '请确认是否要删除此项？'}
      disabled={disabled}
      onConfirm={handleDelete}
      icon={<QuestionCircleOutlined style={{ color: token.colorError }} />}
    >
      <span className={disabled ? 'disabled' : ''}>
        {props.children ? props.children : <a style={{ color: token.colorError }}>删除</a>}
      </span>
    </Popconfirm>
  )
}

export default ExDeleteButton
