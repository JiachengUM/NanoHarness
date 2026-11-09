import { useRef, useState } from 'react'
import { Button, Space } from 'antd'
import type { TableColumnsType } from 'antd'
import Api from '@/apis/task-data'
import ExDeleteButton from '@/components/DeleteButton'
import ExTable from '@/components/Table'
import type { HandleType } from '@/components/Table'
import Form from './form'
import ExDrawer from '@/components/Form/drawer'
import { formatDateTimeByString } from '@/utils/format'
import { useNavigate } from 'react-router'
import useApiModeStore from '@/stores/apiMode'

const App: React.FC = () => {
  const tableRef = useRef<HandleType<Dataset>>(null)
  const [open, setOpen] = useState(false)
  const [formData, setFormData] = useState<Dataset>({})
  const navigate = useNavigate()
  const resolvePath = useApiModeStore((s) => s.resolvePath)

  const searchList = [
    { key: 'name', label: '数据集名称', type: 'input' },
    { key: 'creator', label: '创建人', type: 'input' },
  ]

  const columns: TableColumnsType<Dataset> = [
    {
      title: '数据集名称',
      dataIndex: 'name',
    },
    {
      title: '数据集描述',
      dataIndex: 'description',
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
          <a onClick={() => onDetail(record)}>明细</a>
          <a onClick={() => onEdit(record)}>编辑</a>
          <ExDeleteButton id={record.id} API={Api.advisorDataset.del} onSuccess={() => tableRef.current?.refresh()} />
        </Space>
      ),
    },
  ]

  const onAdd = () => {
    setFormData({})
    setOpen(true)
  }

  const onEdit = (record: Dataset) => {
    setFormData(record)
    setOpen(true)
  }

  const onDetail = (record: Dataset) => {
    navigate(resolvePath(`/other/data/advisor-dataset/${record.id}`))
  }

  const handleSuccess = () => {
    tableRef.current?.refresh()
    setOpen(false)
  }

  return (
    <>
      <ExTable<Dataset>
        ref={tableRef}
        columns={columns}
        api={Api.advisorDataset.page}
        searchProps={{
          searchList: searchList,
          action: (
            <Button type="primary" onClick={onAdd}>
              新增
            </Button>
          ),
        }}
      />

      <ExDrawer open={open} setOpen={setOpen} title={formData.id ? '编辑数据集' : '新增数据集'}>
        <Form formData={formData} onCancel={() => setOpen(false)} onSuccess={handleSuccess} />
      </ExDrawer>
    </>
  )
}

export default App
