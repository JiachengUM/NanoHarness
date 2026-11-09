import React from 'react'
import { Button, Input } from 'antd'
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons'

type Props = {
  value?: string[]
  onChange?: (value: string[]) => void
  placeholder?: string
  disabled?: boolean
  textarea?: boolean
  hideAddButton?: boolean
}

const ArrayInput: React.FC<Props> = ({ value, onChange, placeholder, disabled, textarea, hideAddButton }) => {
  if (value && Array.isArray(value) === false) return <span>数据格式错误</span>

  const InputComponent = textarea ? Input.TextArea : Input
  const showAddButton = !hideAddButton && !disabled
  const showDeleteButton = !disabled

  return (
    <div style={{ flex: 1 }}>
      {(value || []).map((item, index) => {
        return (
          <div
            key={index}
            style={{
              display: 'flex',
              alignItems: textarea ? 'flex-start' : 'center',
              gap: 12,
              marginBottom: 8,
            }}
          >
            <InputComponent
              value={item}
              style={{ flex: 1 }}
              disabled={disabled}
              placeholder={placeholder}
              onChange={(e) => {
                const _value = value ? [...value] : []
                _value[index] = e.target.value
                onChange?.(_value)
              }}
            />
            {showDeleteButton && (
              <MinusCircleOutlined
                style={{ color: 'red', marginTop: textarea ? 8 : 0, cursor: 'pointer' }}
                onClick={() => {
                  if (disabled) return
                  const _value = value ? [...value] : []
                  _value.splice(index, 1)
                  onChange?.(_value)
                }}
              />
            )}
          </div>
        )
      })}
      {showAddButton && (
        <Button
          type="dashed"
          disabled={disabled}
          onClick={() => {
            if (disabled) return
            const _value = value ? [...value] : []
            _value.push('')
            onChange?.(_value)
          }}
          block
          icon={<PlusOutlined />}
        >
          添加
        </Button>
      )}
    </div>
  )
}

export default ArrayInput
