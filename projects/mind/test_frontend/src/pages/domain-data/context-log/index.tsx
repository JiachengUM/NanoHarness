import { useRef, useState } from 'react'
import type { TableColumnsType } from 'antd'
import Api from '@/apis/domain-data'
import ExTable from '@/components/Table'
import type { HandleType } from '@/components/Table'
import { jsonRender } from '@/utils/json'
import { formatDateTimeByString } from '@/utils/format'
import ExDrawer from '@/components/Form/drawer'
import CodeEditor from '@/components/CodeEditor'

const App: React.FC = () => {
  const tableRef = useRef<HandleType<ContextLog>>(null)
  const [open, setOpen] = useState(false)
  const [formData, setFormData] = useState<ContextLog>({})

  const searchList = [
    { key: 'log_id', label: '日志ID', type: 'input' },
    { key: 'log_type', label: '日志类型', type: 'input' },
  ]

  const columns: TableColumnsType<ContextLog> = [
    {
      title: '日志ID',
      dataIndex: 'log_id',
      width: 200,
    },
    {
      title: '类型',
      dataIndex: 'log_type',
      width: 80,
    },
    {
      title: '上下文信息',
      dataIndex: 'context',
      render: (_, record) => jsonRender(record.context),
      ellipsis: true,
    },
    {
      title: '备注',
      dataIndex: 'remark',
    },
    {
      title: '日志时间',
      dataIndex: 'created_time',
      render: (_, record) => formatDateTimeByString(record.created_time),
      width: 180,
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      fixed: 'right',
      render: (_, record) => <a onClick={() => onDetail(record)}>详情</a>,
    },
  ]

  const onDetail = (record: ContextLog) => {
    console.log('日志详情:', record.context)
    setFormData(record)
    setOpen(true)
  }

  return (
    <>
      <ExTable<ContextLog>
        ref={tableRef}
        columns={columns}
        api={Api.contextLog.page}
        searchProps={{
          searchList: searchList,
        }}
      />

      <ExDrawer open={open} setOpen={setOpen} title="车辆信号日志详情">
        <CodeEditor value={JSON.stringify(formData.context, null, 2)} height="100%" readOnly />
      </ExDrawer>
    </>
  )
}

export default App
