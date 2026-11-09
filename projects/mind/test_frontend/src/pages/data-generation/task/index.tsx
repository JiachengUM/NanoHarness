import { useRef, useState } from 'react'
import { Button, Space } from 'antd'
import type { TableColumnsType } from 'antd'
import { useNavigate } from 'react-router'
import Api from '@/apis/data-generation'
import ExTable from '@/components/Table'
import type { HandleType } from '@/components/Table'
import ExDrawer from '@/components/Form/drawer'
import ExDeleteButton from '@/components/DeleteButton'
import { formatDateTimeByString } from '@/utils/format'
import TaskForm from './form'
import useApiModeStore from '@/stores/apiMode'

const GenerationTaskPage: React.FC = () => {
  const tableRef = useRef<HandleType<GenerationTask>>(null)
  const [open, setOpen] = useState(false)
  const [formData, setFormData] = useState<GenerationTask>({})
  const navigate = useNavigate()
  const resolvePath = useApiModeStore((s) => s.resolvePath)

  const columns: TableColumnsType<GenerationTask> = [
    { title: '任务名称', dataIndex: 'name' },
    { title: '描述', dataIndex: 'description', ellipsis: true },
    { title: '创建人', dataIndex: 'creator', width: 100 },
    {
      title: '创建时间',
      dataIndex: 'created_time',
      width: 180,
      render: (value) => formatDateTimeByString(value),
    },
    {
      title: '操作',
      width: 220,
      render: (_, record) => (
        <Space>
          <a onClick={() => navigate(resolvePath(`/data-generation/task/${record.id}/scenarios`), { state: { taskName: record.name } })}>场景</a>
          <a onClick={() => { setFormData(record); setOpen(true) }}>编辑</a>
          <ExDeleteButton
            id={record.id}
            API={Api.generationTask.del}
            onSuccess={() => tableRef.current?.refresh()}
          />
        </Space>
      ),
    },
  ]

  const handleSuccess = () => {
    setOpen(false)
    tableRef.current?.refresh()
  }

  return (
    <>
      <ExTable<GenerationTask>
        ref={tableRef}
        columns={columns}
        api={Api.generationTask.page}
        searchProps={{
          searchList: [{ key: 'name', label: '任务名称', type: 'input' }],
          action: (
            <Button type="primary" onClick={() => { setFormData({}); setOpen(true) }}>
              新增任务
            </Button>
          ),
        }}
      />

      <ExDrawer open={open} setOpen={setOpen} title={formData.id ? '编辑合成场景' : '新增合成场景'}>
        <TaskForm formData={formData} onCancel={() => setOpen(false)} onSuccess={handleSuccess} />
      </ExDrawer>
    </>
  )
}

export default GenerationTaskPage
