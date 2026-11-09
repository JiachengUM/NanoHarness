import { AutoComplete, Button, Input, Space } from 'antd'
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons'
import JsonInput from './json-input'
import ArrayInput from './array-input'
import { filterOption } from '@/utils'
import DatetimePicker from './datetime-picker'
import type { Dayjs } from 'dayjs'

export interface ArrayItemControlProps {
  hideAddButton?: boolean
  hideDeleteButton?: boolean
  maxCount?: number
}

export interface Item {
  label: string
  name: string | string[]
  type: string
  placeholder?: string
  itemList?: Item[]
  options?: OptionItem[]
  props?: ArrayItemControlProps
}

type Props<T> = ArrayItemControlProps & {
  value?: T[]
  onChange?: (value: T[]) => void
  placeholder?: string
  disabled?: boolean
  itemList: Item[]
}

const ArrayItem = <T extends Record<string, string>>({
  value,
  onChange,
  placeholder,
  disabled,
  itemList,
  hideAddButton = false,
  hideDeleteButton = false,
  maxCount,
}: Props<T>) => {
  if (value && Array.isArray(value) === false) return <span>数据格式错误</span>

  const itemCount = (value || []).length
  const atMaxCount = maxCount !== undefined && itemCount >= maxCount
  const showAddButton = !hideAddButton && !atMaxCount && !disabled
  const showDeleteButton = !hideDeleteButton && !disabled

  return (
    <div style={{ flex: 1 }}>
      {(value || []).map((item, index) => {
        return (
          <div
            key={index}
            style={{
              display: 'flex',
              gap: 12,
              marginBottom: 8,
              border: '1px solid #f0f0f0',
              padding: '8px',
              borderRadius: '4px',
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
                          const _value = value ? [...value] : []
                          _value[index] = {
                            ..._value[index],
                            [it.name as string]: e.target.value,
                          }
                          onChange?.(_value)
                        }}
                      ></Input>
                    )}

                    {it.type === 'textarea' && (
                      <Input.TextArea
                        placeholder={it.placeholder || placeholder}
                        disabled={disabled}
                        value={item[it.name as keyof T] as unknown as string}
                        onChange={(e) => {
                          const _value = value ? [...value] : []
                          _value[index] = {
                            ..._value[index],
                            [it.name as string]: e.target.value,
                          }
                          onChange?.(_value)
                        }}
                      ></Input.TextArea>
                    )}

                    {it.type === 'autoComplete' && (
                      <AutoComplete
                        allowClear
                        disabled={disabled}
                        value={item[it.name as keyof T] as unknown as string}
                        placeholder={item.placeholder || `请选择或输入${it.label}`}
                        options={it.options}
                        filterOption={filterOption}
                        onChange={(e) => {
                          const _value = value ? [...value] : []
                          _value[index] = {
                            ..._value[index],
                            [it.name as string]: e,
                          }
                          onChange?.(_value)
                        }}
                      />
                    )}

                    {it.type === 'json' && (
                      <JsonInput
                        disabled={disabled}
                        value={item[it.name as keyof T]}
                        onChange={(e) => {
                          const _value = value ? [...value] : []
                          _value[index] = {
                            ..._value[index],
                            [it.name as string]: e,
                          }
                          onChange?.(_value)
                        }}
                      ></JsonInput>
                    )}

                    {it.type === 'datetime' && (
                      <DatetimePicker
                        value={item[it.name as keyof T] as unknown as string & Dayjs}
                        placeholder={it.placeholder || `请选择${it.label}`}
                        onChange={(e) => {
                          const _value = value ? [...value] : []
                          _value[index] = {
                            ..._value[index],
                            [it.name as string]: e,
                          }
                          onChange?.(_value)
                        }}
                      />
                    )}

                    {it.type === 'arrayInput' && (
                      <ArrayInput
                        disabled={disabled}
                        value={item[it.name as keyof T] as unknown as string[]}
                        onChange={(e) => {
                          const _value = value ? [...value] : []
                          _value[index] = {
                            ..._value[index],
                            [it.name as string]: e,
                          }
                          onChange?.(_value)
                        }}
                      ></ArrayInput>
                    )}

                    {it.type === 'arrayItem' && (
                      <ArrayItem
                        disabled={disabled}
                        value={item[it.name as keyof T] as unknown as Record<string, string>[]}
                        itemList={it.itemList || []}
                        hideAddButton={it.props?.hideAddButton}
                        hideDeleteButton={it.props?.hideDeleteButton}
                        maxCount={it.props?.maxCount}
                        onChange={(e) => {
                          const _value = value ? [...value] : []
                          _value[index] = {
                            ..._value[index],
                            [it.name as string]: e,
                          }
                          onChange?.(_value)
                        }}
                      ></ArrayItem>
                    )}
                  </Space.Compact>
                )
              })}
            </div>
            {showDeleteButton && (
              <MinusCircleOutlined
                style={{ color: 'red', cursor: 'pointer' }}
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
            if (disabled || atMaxCount) return
            const _value = value ? [...value] : []
            _value.push({} as T)
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

export default ArrayItem
