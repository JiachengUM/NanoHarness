import React, { useState } from 'react'
import { Button, Input, Select, Space, Tooltip } from 'antd'
import { MenuOutlined, LoadingOutlined, SendOutlined } from '@ant-design/icons'
import styles from './index.module.less'
import { useOptions } from '@/hooks/options'
import taskApi from '@/apis/task-data'

interface Props {
  loading?: boolean
  disable?: boolean
  onSend: (formData: ChatRequest) => void
  onStop: (formData: ChatRequest) => void
}

const App: React.FC<Props> = ({ loading, disable, onSend }) => {
  const [formData, setFormData] = useState<ChatRequest>({
    message: '',
  })
  const [showMore, setShowMore] = useState<boolean>(false)

  const [datasetId, setDatasetId] = useState<string>()
  const [datasetOptions] = useOptions(taskApi.complexReasoningDataset.list, undefined, (e) => ({
    label: e.name,
    value: e.id,
    data: e,
  }))
  const [inputOptions] = useOptions(taskApi.complexReasoningCase.list, { dataset_id: datasetId }, (e) => ({
    label: e.case_id || '',
    value: e.id,
    data: e,
  }))

  const handleClick = () => {
    if (!formData?.message?.trim()) return
    onSend(formData)
    setFormData({ message: '' })
    setShowMore(false)
  }

  // const handleStop = () => {
  //   onStop(formData)
  //   setFormData({ message: '' })
  //   setShowMore(false)
  // }

  const handleMoreClick = () => {
    setShowMore((prev) => !prev)
  }

  const handleDataChange = (key: string, value: string) => {
    if (key === 'input') {
      const inputData = inputOptions.find((item) => item.value === value)?.data as ComplexReasoningCase
      const item = inputData.user_query_lists?.[0]
      const query = Array.isArray(item) ? item[0]?.content || '' : item?.user_query_list?.[0]?.content || ''
      const _input = {
        query,
      }

      setFormData((prev) => ({ ...prev, message: _input.query }))
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleClick()
    }
  }

  return (
    <div className={styles.chatInput}>
      {showMore && (
        <div className={styles.moreInfo}>
          <Space.Compact>
            <Button style={{ width: 100 }}>数据集</Button>
            <Select style={{ width: 240 }} onChange={(e) => setDatasetId(e)} options={datasetOptions}></Select>
            <Button style={{ width: 100 }}>测试用例</Button>
            <Select
              style={{ width: 280 }}
              onChange={(e) => handleDataChange('input', e)}
              options={inputOptions}
            ></Select>
          </Space.Compact>
        </div>
      )}

      <div className={styles.inputItem}>
        <Input.TextArea
          value={formData.message}
          onChange={(e) => setFormData((prev) => ({ ...prev, message: e.target.value }))}
          placeholder="发送消息"
          autoSize={{ minRows: 1, maxRows: 12 }}
          style={{ padding: '12px 40px', borderRadius: 8 }}
          onKeyDown={handleKeyDown}
        />

        <div className={styles.menuButton}>
          <Tooltip title="更多" placement="top">
            <Button icon={<MenuOutlined />} onClick={handleMoreClick} type="text" />
          </Tooltip>
        </div>

        <div className={styles.sendButton}>
          {loading && (
            <Tooltip title="停止" placement="top">
              <LoadingOutlined />
              {/* <Button icon={<PauseOutlined />} onClick={handleStop} disabled={disable} type="text" /> */}
            </Tooltip>
          )}
          {!loading && (
            <Tooltip title="发送" placement="top">
              <Button
                icon={<SendOutlined />}
                onClick={handleClick}
                disabled={disable || !formData?.message?.trim()}
                type="text"
              />
            </Tooltip>
          )}
        </div>
      </div>
    </div>
  )
}

export default App
