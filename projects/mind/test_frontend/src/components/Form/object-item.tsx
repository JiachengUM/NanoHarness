import { Button, Input, Space } from 'antd'
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons'
import JsonInput from './json-input'
import type { Item } from './array-item'
import ArrayItem from './array-item'

type Props<T> = {
  value?: Record<string, T>
  baseKey?: string
  onChange?: (value: Record<string, T>) => void
  placeholder?: string
  disabled?: boolean
  itemList: Item[]
}

const ObjectItem = <T extends Record<string, string>>({
  value,
  onChange,
  baseKey = 'item',
  placeholder,
  disabled,
  itemList,
}: Props<T>) => {
  if (value && typeof value !== 'object') return <span>数据格式错误</span>

  const getKey = (e: Record<string, T> = {}) => {
    let length = 1

    function padToThreeDigits(num: number) {
      return num.toString().padStart(3, '0')
    }

    while (Object.keys(e || {}).includes(`${baseKey}_${padToThreeDigits(length)}`)) {
      length += 1
    }

    return `${baseKey}_${padToThreeDigits(length)}`
  }

  return (
    <div>
      {Object.keys(value || {}).map((key, index) => {
        const item = value ? (value as Record<string, T>)[key] : ({} as T)
        return (
          <div
            key={index}
            style={{
              display: 'flex',
              gap: 12,
              margin: '16px 0 24px',
              border: '1px solid #f0f0f0',
              padding: '16px 8px 8px',
              borderRadius: '4px',
              position: 'relative',
            }}
          >
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {itemList.map((it) => {
                return (
                  <Space.Compact key={String(it.name)}>
                    <Button>{it.label}</Button>
                    {it.type === 'input' && (
                      <Input
                        placeholder={it.placeholder || placeholder}
                        disabled={disabled}
                        value={item[it.name as keyof T] as unknown as string}
                        onChange={(e) => {
                          const _value = value ? { ...value } : {}
                          _value[key] = {
                            ..._value[key],
                            [it.name as string]: e.target.value,
                          }
                          onChange?.(_value)
                        }}
                      ></Input>
                    )}

                    {it.type === 'json' && (
                      <JsonInput
                        disabled={disabled}
                        value={item[it.name as keyof T]}
                        onChange={(e) => {
                          const _value = value ? { ...value } : {}
                          _value[key] = {
                            ..._value[key],
                            [it.name as string]: e,
                          }
                          onChange?.(_value)
                        }}
                      ></JsonInput>
                    )}

                    {it.type === 'arrayItem' && (
                      <ArrayItem
                        value={item[it.name as keyof T] as unknown as Record<string, string>[]}
                        disabled={disabled}
                        itemList={it.itemList || []}
                        onChange={(e) => {
                          const _value = value ? { ...value } : {}
                          _value[key] = {
                            ..._value[key],
                            [it.name as string]: e,
                          }
                          onChange?.(_value)
                        }}
                      />
                    )}
                  </Space.Compact>
                )
              })}
            </div>
            <MinusCircleOutlined
              disabled={disabled}
              style={{ color: 'red' }}
              onClick={() => {
                const _value = value ? { ...value } : {}
                delete _value[key]
                onChange?.(_value)
              }}
            />

            <div
              style={{
                position: 'absolute',
                top: -12,
                left: 8,
                background: 'white',
                padding: '0 8px',
                border: '1px solid #f0f0f0',
                borderRadius: '4px',
              }}
            >
              {key}
            </div>
          </div>
        )
      })}
      <Button
        type="dashed"
        onClick={() => {
          const _value = value ? { ...value } : {}
          _value[getKey(_value)] = {} as T
          onChange?.(_value)
        }}
        block
        icon={<PlusOutlined />}
      >
        添加
      </Button>
    </div>
  )
}

export default ObjectItem
