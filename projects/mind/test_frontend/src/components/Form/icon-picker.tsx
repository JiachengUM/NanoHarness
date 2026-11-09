import React, { useState } from 'react'
import { Input, List, Modal } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import * as icons from '@ant-design/icons'

const { Search } = Input

type IconKeys = keyof typeof icons

// 获取所有 Ant Design 图标
const allIcons = Object.keys(icons)
  .filter(key => key.endsWith('Outlined')) // 只选择 Outlined 风格的图标
  .map(key => ({
    name: key,
    component: icons[key as IconKeys],
  }))

type Props = {
  value?: string
  onChange?: (iconName: string) => void
}

const App: React.FC<Props> = ({ value, onChange }) => {
  const [open, setOpen] = useState(false)
  const [searchText, setSearchText] = useState('')
  const [selectedIcon, setSelectedIcon] = useState(value)

  // 过滤图标
  const filteredIcons = allIcons.filter(icon => icon.name.toLowerCase().includes(searchText.toLowerCase()))

  // 选择图标
  const handleSelectIcon = (iconName: string) => {
    setSelectedIcon(iconName)
    onChange?.(iconName)
    setOpen(false)
  }

  return (
    <>
      {/* 图标选择按钮 */}
      <div
        style={{
          width: 26,
          height: 26,
          border: '1px dashed #ccc',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
        }}
        onClick={() => setOpen(true)}
      >
        {selectedIcon ? (
          React.createElement(icons[selectedIcon as IconKeys] as React.FC<{ style?: React.CSSProperties }>, {
            style: { fontSize: 24 },
          })
        ) : (
          <SearchOutlined style={{ fontSize: 24 }} />
        )}
      </div>

      {/* 图标选择弹窗 */}
      <Modal
        title="选择图标"
        open={open}
        onCancel={() => setOpen(false)}
        footer={null}
        width={800}
      >
        <Search
          placeholder="搜索图标"
          value={searchText}
          onChange={e => setSearchText(e.target.value)}
          style={{ marginBottom: 16 }}
        />
        <List
          grid={{ gutter: 16, column: 6 }}
          dataSource={filteredIcons}
          style={{ height: 400, paddingRight: 8, overflow: 'auto' }}
          renderItem={icon => (
            <List.Item>
              <div
                style={{
                  padding: 16,
                  border: '1px solid #eee',
                  textAlign: 'center',
                  cursor: 'pointer',
                  backgroundColor: selectedIcon === icon.name ? '#e6f7ff' : '#fff',
                }}
                onClick={() => handleSelectIcon(icon.name)}
              >
                {React.createElement(icon.component as React.FC<{ style?: React.CSSProperties }>, {
                  style: { fontSize: 24 },
                })}
                <div style={{ marginTop: 8, fontSize: 12 }}>{icon.name}</div>
              </div>
            </List.Item>
          )}
        />
      </Modal>
    </>
  )
}

export default App
