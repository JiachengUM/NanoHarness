import { useMemo, useState } from 'react'
import { Button, Modal, Select, Space, Tag } from 'antd'

type Props = {
  value?: string[]
  onChange?: (value: string[]) => void
  placeholder?: string
  disabled?: boolean
  leafTagOptions?: string[]
  leafTagsLoading?: boolean
}

const TagListInput: React.FC<Props> = ({
  value,
  onChange,
  placeholder = '暂未选择测试维度',
  disabled,
  leafTagOptions = [],
  leafTagsLoading,
}) => {
  const [pickerOpen, setPickerOpen] = useState(false)
  const [picked, setPicked] = useState<string[]>([])

  const tags = value || []

  const availableOptions = useMemo(() => {
    const selected = new Set(tags)
    return leafTagOptions
      .filter((tag) => !selected.has(tag))
      .map((tag) => ({ label: tag, value: tag }))
  }, [leafTagOptions, tags])

  const openPicker = () => {
    setPicked([])
    setPickerOpen(true)
  }

  const closePicker = () => {
    setPickerOpen(false)
    setPicked([])
  }

  const confirmPick = () => {
    const merged = [...tags]
    for (const tag of picked) {
      if (!merged.includes(tag)) merged.push(tag)
    }
    onChange?.(merged)
    closePicker()
  }

  const removeTag = (tag: string) => {
    onChange?.(tags.filter((item) => item !== tag))
  }

  return (
    <>
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 8,
            minHeight: 32,
            padding: tags.length ? '4px 0' : 0,
          }}
        >
          {tags.length ? (
            tags.map((tag) => (
              <Tag
                key={tag}
                closable={!disabled}
                onClose={(event) => {
                  event.preventDefault()
                  removeTag(tag)
                }}
              >
                {tag}
              </Tag>
            ))
          ) : (
            <span style={{ color: 'rgba(0, 0, 0, 0.45)', lineHeight: '32px' }}>{placeholder}</span>
          )}
        </div>
        <Button
          type="dashed"
          loading={leafTagsLoading}
          disabled={disabled || !leafTagOptions.length}
          onClick={openPicker}
        >
          从测试维度中选择添加
        </Button>
      </Space>
      <Modal
        title="从测试维度中选择添加"
        open={pickerOpen}
        onCancel={closePicker}
        onOk={confirmPick}
        okButtonProps={{ disabled: !picked.length }}
        destroyOnHidden
      >
        <Select
          mode="multiple"
          showSearch
          placeholder="搜索并选择叶子标签"
          options={availableOptions}
          value={picked}
          onChange={setPicked}
          style={{ width: '100%' }}
          optionFilterProp="label"
        />
      </Modal>
    </>
  )
}

export default TagListInput
