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
  const tableRef = useRef<HandleType<IntentRun>>(null)
  const [open, setOpen] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [formData, setFormData] = useState<IntentRun>({})

  const searchList = [{ key: 'creator', label: '创建人', type: 'input' }]

  const columns: TableColumnsType<IntentRun> = [
    {
      title: '意图识别查询',
      dataIndex: ['input', 'query'],
      ellipsis: true,
    },
    {
      title: '意图分类',
      dataIndex: ['output', 'intent_type'],
    },
    {
      title: '耗时',
      dataIndex: 'total_time',
      width: 100,
    },
    {
      title: '输入',
      dataIndex: 'input',
      render: (_, record) => jsonRender(record.input),
      ellipsis: true,
    },
    {
      title: '输出',
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
          <ExDeleteButton id={record.id} API={Api.intentRun.del} onSuccess={() => tableRef.current?.refresh()} />
        </Space>
      ),
    },
  ]

  const onDetail = (record: IntentRun) => {
    setFormData(record)
    setDetailOpen(true)
  }

  const onEval = (record: IntentRun) => {
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
      <ExTable<IntentRun>
        ref={tableRef}
        columns={columns}
        api={Api.intentRun.page}
        searchProps={{
          searchList: searchList,
          // action: (
          //   <Button type="primary" onClick={onExport}>
          //     导出
          //   </Button>
          // ),
        }}
      />

      <ExDrawer open={open} setOpen={setOpen} title="意图识别执行评价">
        <Detail
          record={formData}
          defaultActiveKey={['manual-eval']}
          evalForm={<EvalForm record={formData} onCancel={() => setOpen(false)} onSuccess={handleSuccess} />}
        />
      </ExDrawer>

      <ExDrawer open={detailOpen} setOpen={setDetailOpen} title="意图识别执行明细">
        <Detail record={formData} />
      </ExDrawer>
    </>
  )
}

export default App
