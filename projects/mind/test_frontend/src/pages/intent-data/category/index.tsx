import { useRef, useState } from 'react'
import { Button, Space } from 'antd'
import type { TableColumnsType } from 'antd'
import Api from '@/apis/intent'
import ExDeleteButton from '@/components/DeleteButton'
import ExTable from '@/components/Table'
import type { HandleType } from '@/components/Table'
// import category_json from '@/assets/template/intent/category.json'
import Form from './form'
import ExDrawer from '@/components/Form/drawer'
import { formatDateTimeByString } from '@/utils/format'

const App: React.FC = () => {
  const tableRef = useRef<HandleType<Category>>(null)
  const [open, setOpen] = useState(false)
  const [formData, setFormData] = useState<Category>({})

  const searchList = [
    { key: 'name', label: '类别名称', type: 'input' },
    { key: 'creator', label: '创建人', type: 'user' },
  ]

  const columns: TableColumnsType<Category> = [
    {
      title: '类别分组',
      dataIndex: 'group',
    },
    {
      title: '类别名称',
      dataIndex: 'name',
    },
    {
      title: '类别定义',
      dataIndex: 'definition',
      ellipsis: true,
    },
    {
      title: '典型正例',
      dataIndex: 'example',
      render: (_, record) => record.example?.join('\n'),
      ellipsis: true,
    },
    {
      title: '典型负例',
      dataIndex: 'example_neg',
      render: (_, record) => record.example_neg?.join('\n'),
      ellipsis: true,
    },
    {
      title: '注意事项',
      dataIndex: 'notice',
      render: (_, record) => record.notice?.join('\n'),
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
      width: 110,
      render: (_, record) => (
        <Space size="middle">
          <a onClick={() => onEdit(record)}>编辑</a>
          <ExDeleteButton id={record.id} API={Api.category.del} onSuccess={() => tableRef.current?.refresh()} />
        </Space>
      ),
    },
  ]

  const onAdd = () => {
    setFormData({ group: '默认分组' })
    setOpen(true)
  }

  const onEdit = (record: Category) => {
    setFormData(record)
    setOpen(true)
  }

  const handleSuccess = () => {
    tableRef.current?.refresh()
    setOpen(false)
  }

  return (
    <>
      <ExTable<Category>
        ref={tableRef}
        columns={columns}
        api={Api.category.page}
        searchProps={{
          searchList: searchList,
          action: (
            <Button type="primary" onClick={onAdd}>
              新增
            </Button>
          ),
        }}
      />

      <ExDrawer open={open} setOpen={setOpen} title={formData.id ? '编辑意图类别' : '新增意图类别'}>
        <Form formData={formData} onCancel={() => setOpen(false)} onSuccess={handleSuccess} />
      </ExDrawer>
    </>
  )
}

export default App
