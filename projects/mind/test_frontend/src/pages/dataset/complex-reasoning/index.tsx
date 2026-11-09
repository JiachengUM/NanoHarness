import { useRef, useState } from 'react'
import { Button, Space } from 'antd'
import type { TableColumnsType } from 'antd'
import Api from '@/apis/task-data'
import ExDeleteButton from '@/components/DeleteButton'
import ExTable from '@/components/Table'
import type { HandleType } from '@/components/Table'
import Form from './form'
import CopyForm from './copy-form'
import ExDrawer from '@/components/Form/drawer'
import { formatDateTimeByString } from '@/utils/format'
import { useNavigate } from 'react-router'
import useApiModeStore from '@/stores/apiMode'

const App: React.FC = () => {
  const tableRef = useRef<HandleType<ComplexReasoningDataset>>(null)
  const [open, setOpen] = useState(false)
  const [copyOpen, setCopyOpen] = useState(false)
  const [formData, setFormData] = useState<ComplexReasoningDataset>({})
  const [copyDatasetId, setCopyDatasetId] = useState<string>()
  const navigate = useNavigate()
  const resolvePath = useApiModeStore((s) => s.resolvePath)

  const searchList = [
    { key: 'name', label: '数据集名称', type: 'input' },
    { key: 'creator', label: '创建人', type: 'input' },
  ]

  const columns: TableColumnsType<ComplexReasoningDataset> = [
    {
      title: 'ID',
      dataIndex: 'id',
    },
    {
      title: '数据集名称',
      dataIndex: 'name',
    },
    {
      title: '用例数量',
      dataIndex: 'item_count',
    },
    {
      title: '数据集描述',
      dataIndex: 'description',
    },
    {
      title: '创建人',
      dataIndex: 'creator',
      width: 80,
    },
    {
      title: '创建时间',
      dataIndex: 'created_time',
      render: (_, record) => formatDateTimeByString(record.created_time),
      width: 160,
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_, record) => (
        <Space size="middle">
          <a onClick={() => onCopy(record)}>复制</a>
          <a onClick={() => onDetail(record)}>明细</a>
          <a onClick={() => onEdit(record)}>编辑</a>
          <ExDeleteButton
            id={record.id}
            API={Api.complexReasoningDataset.del}
            onSuccess={() => tableRef.current?.refresh()}
          />
        </Space>
      ),
    },
  ]

  const onAdd = () => {
    setFormData({})
    setOpen(true)
  }

  const onEdit = (record: ComplexReasoningDataset) => {
    setFormData(record)
    setOpen(true)
  }

  const onDetail = (record: ComplexReasoningDataset) => {
    navigate(resolvePath(`/data/complex-reasoning-dataset/${record.id}`))
  }

  const onCopy = (record: ComplexReasoningDataset) => {
    setCopyDatasetId(record.id)
    setCopyOpen(true)
  }

  const handleSuccess = () => {
    tableRef.current?.refresh()
    setOpen(false)
    setCopyOpen(false)
  }

  return (
    <>
      <ExTable<ComplexReasoningDataset>
        ref={tableRef}
        columns={columns}
        api={Api.complexReasoningDataset.page}
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

      <ExDrawer open={copyOpen} setOpen={setCopyOpen} title="复制该数据集为新数据集">
        <CopyForm dataset_id={copyDatasetId} onCancel={() => setCopyOpen(false)} onSuccess={handleSuccess} />
      </ExDrawer>
    </>
  )
}

export default App
