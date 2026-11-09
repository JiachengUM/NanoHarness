import { useRef, useState } from 'react'
import { Space } from 'antd'
import type { TableColumnsType } from 'antd'
import Api from '@/apis/task-data'
import ExDeleteButton from '@/components/DeleteButton'
import ExTable from '@/components/Table'
import type { HandleType } from '@/components/Table'
import { formatDateTimeByString } from '@/utils/format'
import ExDrawer from '@/components/Form/drawer'
import EvalForm from './eval-form'
import Detail from './detail'
import { jsonRender } from '@/utils/json'

const App: React.FC = () => {
  const tableRef = useRef<HandleType<AdvisorRun>>(null)
  const [open, setOpen] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [formData, setFormData] = useState<AdvisorRun>({})

  const searchList = [{ key: 'creator', label: '创建人', type: 'input' }]

  const columns: TableColumnsType<AdvisorRun> = [
    {
      title: '测试模块',
      dataIndex: 'advise_type',
      width: 100,
    },
    {
      title: '事件信息',
      dataIndex: 'event',
      render: (_, record) => record.input?.event,
      ellipsis: true,
    },
    {
      title: 'advisor输入',
      dataIndex: 'input',
      render: (_, record) => jsonRender(record.input),
      ellipsis: true,
    },
    {
      title: 'advisor输出',
      dataIndex: 'output',
      render: (_, record) => jsonRender(record.output),
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
          <a onClick={() => onDetail(record)}>详情</a>
          <a onClick={() => onEval(record)}>评价</a>
          <ExDeleteButton id={record.id} API={Api.advisorRun.del} onSuccess={() => tableRef.current?.refresh()} />
        </Space>
      ),
    },
  ]

  const onDetail = (record: AdvisorRun) => {
    setFormData(record)
    setDetailOpen(true)
  }

  const onEval = (record: AdvisorRun) => {
    setFormData(record)
    setOpen(true)
  }

  const handleSuccess = () => {
    tableRef.current?.refresh()
    setOpen(false)
  }

  // const onExport = () => {}

  return (
    <>
      <ExTable<AdvisorRun>
        ref={tableRef}
        columns={columns}
        api={Api.advisorRun.page}
        searchProps={{
          searchList: searchList,
          // action: (
          //   <Button type="primary" onClick={onExport}>
          //     导出
          //   </Button>
          // ),
        }}
      />

      <ExDrawer open={open} setOpen={setOpen} title="advisor执行评价">
        <Detail
          record={formData}
          defaultActiveKey={['manual-eval']}
          evalForm={<EvalForm record={formData} onCancel={() => setOpen(false)} onSuccess={handleSuccess} />}
        />
      </ExDrawer>

      <ExDrawer open={detailOpen} setOpen={setDetailOpen} title="advisor执行明细">
        <Detail record={formData} />
      </ExDrawer>
    </>
  )
}

export default App
