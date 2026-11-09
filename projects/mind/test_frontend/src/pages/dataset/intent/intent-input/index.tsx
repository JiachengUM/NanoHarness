import { useMemo, useRef, useState } from 'react'
import { Button, Space } from 'antd'
import type { TableColumnsType } from 'antd'
import Api from '@/apis/task-data'
import ExDeleteButton from '@/components/DeleteButton'
import ExTable from '@/components/Table'
import type { HandleType } from '@/components/Table'
import Form from './form'
import ExDrawer from '@/components/Form/drawer'
import { formatDateTimeByString } from '@/utils/format'
import { useParams } from 'react-router'
import { removeMetaFields } from '@/utils/json'

const App: React.FC = () => {
  const tableRef = useRef<HandleType<IntentInput>>(null)
  const [open, setOpen] = useState(false)
  const [formData, setFormData] = useState<IntentInput>({})
  const { dataset_id } = useParams()

  const params = useMemo(() => ({ dataset_id }), [dataset_id])

  const searchList = [
    { key: 'query', label: 'query', type: 'input' },
    { key: 'creator', label: '创建人', type: 'input' },
  ]

  const columns: TableColumnsType<IntentInput> = [
    {
      title: '意图查询',
      dataIndex: 'query',
    },
    {
      title: '历史对话',
      dataIndex: 'messages',
      render: (_, record) => (record.messages?.length ? JSON.stringify(record.messages) : ''),
      ellipsis: true,
    },
    {
      title: '创建人',
      dataIndex: 'creator',
      width: 100,
    },
    {
      title: '创建时间',
      dataIndex: 'created_time',
      render: (_, record) => formatDateTimeByString(record.created_time),
      width: 180,
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      render: (_, record) => (
        <Space size="middle">
          <a onClick={() => onCopy(record)}>复制</a>
          <a onClick={() => onEdit(record)}>编辑</a>
          <ExDeleteButton id={record.id} API={Api.intentInput.del} onSuccess={() => tableRef.current?.refresh()} />
        </Space>
      ),
    },
  ]

  const onAdd = () => {
    setFormData({ dataset_id })
    setOpen(true)
  }

  const onEdit = (record: IntentInput) => {
    setFormData(record)
    setOpen(true)
  }

  const onCopy = (record: IntentInput) => {
    setFormData(removeMetaFields(record))
    setOpen(true)
  }

  const handleSuccess = () => {
    tableRef.current?.refresh()
    setOpen(false)
  }

  return (
    <>
      <ExTable<IntentInput>
        ref={tableRef}
        params={params}
        columns={columns}
        api={Api.intentInput.page}
        searchProps={{
          searchList: searchList,
          action: (
            <Button type="primary" onClick={onAdd}>
              新增
            </Button>
          ),
        }}
      />

      <ExDrawer open={open} setOpen={setOpen} title={formData.id ? '编辑测试用例' : '新增测试用例'}>
        <Form formData={formData} onCancel={() => setOpen(false)} onSuccess={handleSuccess} />
      </ExDrawer>
    </>
  )
}

export default App
