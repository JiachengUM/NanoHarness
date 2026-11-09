import { useRef, useState } from 'react'
import { Button, message, Space } from 'antd'
import type { TableColumnsType } from 'antd'
import Api from '@/apis/domain-data'
import ExDeleteButton from '@/components/DeleteButton'
import ExTable from '@/components/Table'
import type { HandleType } from '@/components/Table'
import Form from './form'
import ExDrawer from '@/components/Form/drawer'
import memory_json from '@/assets/template/domain/memory.json'
import { jsonRender, removeMetaFields } from '@/utils/json'
import { formatDateTimeByString } from '@/utils/format'

const App: React.FC = () => {
  const tableRef = useRef<HandleType<EpisodicMemory>>(null)
  const [open, setOpen] = useState(false)
  const [formData, setFormData] = useState<EpisodicMemory>({})
  const [messageApi, contextHolder] = message.useMessage()

  const searchList = [{ key: 'creator', label: '创建人', type: 'input' }]

  const columns: TableColumnsType<EpisodicMemory> = [
    {
      title: '摘要信息',
      dataIndex: 'brief',
    },
    {
      title: '实体信息',
      dataIndex: 'entity',
      render: (_, record) => jsonRender(record.entity),
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
          <ExDeleteButton id={record.id} API={Api.memory.del} onSuccess={() => tableRef.current?.refresh()} />
        </Space>
      ),
    },
  ]

  const onAdd = () => {
    setFormData({ brief: '', entity: memory_json as unknown as EpisodicMemoryEntity })
    setOpen(true)
  }

  const onCopy = (record: EpisodicMemory) => {
    try {
      const _record = JSON.parse(JSON.stringify(removeMetaFields(record)))
      delete _record.id
      setFormData(_record)
      setOpen(true)
    } catch {
      messageApi.error('复制失败！')
    }
  }

  const onEdit = (record: EpisodicMemory) => {
    setFormData(record)
    setOpen(true)
  }

  const handleSuccess = () => {
    tableRef.current?.refresh()
    setOpen(false)
  }

  return (
    <>
      {contextHolder}
      <ExTable<EpisodicMemory>
        ref={tableRef}
        columns={columns}
        api={Api.memory.page}
        searchProps={{
          searchList: searchList,
          action: (
            <Button type="primary" onClick={onAdd}>
              新增
            </Button>
          ),
        }}
      />

      <ExDrawer open={open} setOpen={setOpen} title={formData.id ? '编辑记忆信息' : '新增记忆信息'}>
        <Form formData={formData} onCancel={() => setOpen(false)} onSuccess={handleSuccess} />
      </ExDrawer>
    </>
  )
}

export default App
