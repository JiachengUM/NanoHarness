import { Button } from 'antd'
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons'
import ArrayItem from './array-item'
import type { ArrayItemControlProps, Item } from './array-item'

export type { Item }

type Props<T> = ArrayItemControlProps & {
  value?: T[][]
  onChange?: (value: T[][]) => void
  placeholder?: string
  disabled?: boolean
  itemList: Item[]
}

const ArrayArrayItem = <T extends Record<string, string>>({
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

  const showAddGroupButton = !hideAddButton && !disabled
  const showDeleteGroupButton = !hideDeleteButton && !disabled

  return (
    <div style={{ flex: 1 }}>
      {(value || []).map((group, groupIndex) => {
        return (
          <div
            key={groupIndex}
            style={{
              marginBottom: 12,
              border: '1px solid #d9d9d9',
              padding: '8px',
              borderRadius: '4px',
            }}
          >
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
              <div style={{ flex: 1 }}>
                <ArrayItem
                  value={group}
                  placeholder={placeholder}
                  disabled={disabled}
                  itemList={itemList}
                  hideAddButton={hideAddButton}
                  hideDeleteButton={hideDeleteButton}
                  maxCount={maxCount}
                  onChange={(newGroup) => {
                    const _value = value ? [...value] : []
                    _value[groupIndex] = newGroup as T[]
                    onChange?.(_value)
                  }}
                />
              </div>
              {showDeleteGroupButton && (
                <MinusCircleOutlined
                  style={{ color: 'red', marginTop: 8, cursor: 'pointer' }}
                  onClick={() => {
                    if (disabled) return
                    const _value = value ? [...value] : []
                    _value.splice(groupIndex, 1)
                    onChange?.(_value)
                  }}
                />
              )}
            </div>
          </div>
        )
      })}
      {showAddGroupButton && (
        <Button
          type="dashed"
          disabled={disabled}
          onClick={() => {
            if (disabled) return
            const _value = value ? [...value] : []
            _value.push([])
            onChange?.(_value)
          }}
          block
          icon={<PlusOutlined />}
        >
          添加组
        </Button>
      )}
    </div>
  )
}

export default ArrayArrayItem
