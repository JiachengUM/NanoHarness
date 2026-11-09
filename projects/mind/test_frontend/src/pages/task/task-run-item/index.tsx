import { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Space, Spin } from 'antd'
import type { TableColumnsType } from 'antd'
import Api from '@/apis/task-data'
// import ExDeleteButton from '@/components/DeleteButton'
import ExTable from '@/components/Table'
import type { HandleType } from '@/components/Table'
import { formatDateTimeByString } from '@/utils/format'
import { useParams } from 'react-router'
import { useOptions } from '@/hooks/options'
import { getLabelById } from '@/utils'
import ExDrawer from '@/components/Form/drawer'
import Detail from './detail'
import EvalForm from './eval-form'
import BuildForm from '@/pages/dataset/complex-reasoning/dataset-build/form'
import { IS_PASS_OPTIONS, TASK_RUN_ITEM_STATUS_OPTIONS } from '@/constants/task'

const passRender = (is_pass: boolean | null) => (is_pass === true ? '通过' : is_pass === false ? '未通过' : '')

const App: React.FC = () => {
  const tableRef = useRef<HandleType<TaskRunItem>>(null)
  const { task_run_id } = useParams()
  const [open, setOpen] = useState(false)
  const [evalOpen, setEvalOpen] = useState(false)
  const [record, setRecord] = useState<TaskRunItem>()
  const [loading, setLoading] = useState(false)
  const [currentData, setCurrentData] = useState<TaskRunItem[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [changeEnable, setChangeEnable] = useState({ pre: true, next: true })
  const [openBuild, setOpenBuild] = useState(false)
  const [buildParams, setBuildParams] = useState<DatasetBuildParams>({ task_run_item_ids: [] })
  const params = useMemo(() => ({ task_run_id }), [task_run_id])
  const [taskOptions] = useOptions(Api.task.list)
  const [taskRunOptions] = useOptions(Api.taskRun.list)
  const taskRun = useMemo(
    () => taskRunOptions.find((item) => item.value === task_run_id)?.data as TaskRun,
    [taskRunOptions, task_run_id]
  )
  const task = useMemo(
    () => taskOptions.find((item) => item.value === taskRun?.task_id)?.data as Task,
    [taskOptions, taskRun?.task_id]
  )

  const [datasetItemOptions] = useOptions(Api.complexReasoningCase.list, { dataset_id: task?.dataset_id })

  const searchList = [
    { key: 'llm_evaluation_is_pass', label: '模型评价', type: 'select', options: IS_PASS_OPTIONS },
    { key: 'status', label: '运行状态', type: 'select', options: TASK_RUN_ITEM_STATUS_OPTIONS },
    { key: 'tag', label: '标签', type: 'input' },
  ]

  const columns: TableColumnsType<TaskRunItem> = [
    {
      title: '序号',
      dataIndex: 'index',
      width: 60,
      fixed: 'left',
      render: (_, record, index) => index + 1,
    },
    {
      title: '测试任务',
      dataIndex: 'task_run_id',
      render: (id) => {
        const taskRun = taskRunOptions.find((item) => item.value === id)?.data as TaskRun
        return getLabelById(taskRun?.task_id, taskOptions)
      },
    },
    {
      title: '测试用例ID',
      dataIndex: 'dataset_item_id',
      render: (id) => {
        const datasetItem = datasetItemOptions.find((item) => item.value === id)?.data as ComplexReasoningCase
        return datasetItem?.case_id || ''
      },
    },
    {
      title: '模型评价',
      dataIndex: ['eval', 'llm_evaluation', 'is_pass'],
      render: passRender,
      width: 100,
    },
    {
      title: '人工评价',
      dataIndex: ['eval', 'human_evaluation', 'score'],
      render: (score) => score ?? '',
      width: 100,
    },
    {
      title: '状态',
      dataIndex: 'status',
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
      width: 120,
      fixed: 'right',
      render: (_, record) => (
        <Space size="middle">
          <a onClick={() => onDetail(record)}>详情</a>
          <a onClick={() => onEval(record)}>评价</a>
          {/* <ExDeleteButton id={record.id} API={Api.taskRunItem.del} onSuccess={() => tableRef.current?.refresh()} /> */}
        </Space>
      ),
    },
  ]

  const onDetail = (record: TaskRunItem) => {
    if (!record.id) return

    setOpen(true)
    setLoading(true)
    Api.taskRunItem
      .get(record.id)
      .then((res) => {
        setRecord(res)
        checkChangeEnable(res)
      })
      .finally(() => setLoading(false))
  }

  const onEval = (record: TaskRunItem) => {
    setRecord(record)
    setEvalOpen(true)
  }

  const onIntercept = (data: TaskRunItem[]) => {
    setCurrentData(data)
    return data
  }

  const checkChangeEnable = (record: TaskRunItem) => {
    const currentIndex = currentData.findIndex((item) => item.id === record?.id)
    setCurrentIndex(currentIndex)

    const preEnable = currentIndex > 0
    const nextEnable = currentIndex < (currentData.length || 0) - 1
    setChangeEnable((prev) => ({ ...prev, pre: preEnable, next: nextEnable }))
  }

  const changeDetail = (next = true) => {
    if (!currentData.length || !open || loading) return
    if (next && !changeEnable.next) return
    if (!next && !changeEnable.pre) return

    const newIndex = next ? currentIndex + 1 : currentIndex - 1
    const newRecord = currentData[newIndex]
    console.log(newIndex, newRecord)

    onDetail(newRecord)
  }

  const changeDetailRef = useRef(changeDetail)
  useEffect(() => {
    changeDetailRef.current = changeDetail
  })

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (evalOpen) return

      const preKeys = ['ArrowUp', 'ArrowLeft', 'w', 'W']
      const nextKeys = ['ArrowDown', 'ArrowRight', 's', 'S']

      if (preKeys.includes(e.key)) {
        changeDetailRef.current(false)
      } else if (nextKeys.includes(e.key)) {
        changeDetailRef.current(true)
      }
    }

    window.addEventListener('keydown', handleKeyDown)

    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [evalOpen])

  return (
    <>
      <ExTable<TaskRunItem>
        ref={tableRef}
        params={params}
        columns={columns}
        api={Api.taskRunItem.list}
        intercept={onIntercept}
        action={
          <Button type="primary" disabled={!buildParams.task_run_item_ids?.length} onClick={() => setOpenBuild(true)}>
            构建数据集
          </Button>
        }
        searchProps={{
          searchList: searchList,
        }}
        tableProps={{
          pagination: false,
          virtual: true,
          scroll: { x: 1000 },
          rowSelection: {
            columnWidth: 50,
            selectedRowKeys: buildParams.task_run_item_ids,
            onChange: (selectedRowKeys) =>
              setBuildParams((prev) => ({ ...prev, task_run_item_ids: selectedRowKeys as string[] })),
          },
        }}
      />

      <ExDrawer
        open={open}
        setOpen={setOpen}
        loading={loading}
        extra={
          <Space size="middle">
            <Button type="primary" disabled={!record?.id || loading} onClick={() => record && onEval(record)}>
              {record?.eval?.human_evaluation?.score != null
                ? `人工评价 (${record.eval.human_evaluation.score})`
                : '人工评价'}
            </Button>
            <Button disabled={!changeEnable.pre || loading} onClick={() => changeDetail(false)}>
              上一条
            </Button>
            <Button type="primary" disabled={!changeEnable.next || loading} onClick={() => changeDetail(true)}>
              下一条
            </Button>
          </Space>
        }
        width="80%"
        title="任务运行详情"
      >
        {record && (
          <Spin spinning={loading}>
            <Detail
              record={record}
              taskOptions={taskOptions}
              taskRunOptions={taskRunOptions}
              datasetItemOptions={datasetItemOptions}
            />
          </Spin>
        )}
      </ExDrawer>

      <ExDrawer open={evalOpen} setOpen={setEvalOpen} title="测试用例人工评价">
        {record && (
          <EvalForm
            data={record}
            onSuccess={() => {
              setEvalOpen(false)
              tableRef.current?.refresh()
            }}
            onCancel={() => {
              setEvalOpen(false)
            }}
          />
        )}
      </ExDrawer>

      <ExDrawer open={openBuild} setOpen={setOpenBuild} title="构建数据集">
        <BuildForm
          formData={buildParams}
          setFormData={setBuildParams}
          onSuccess={() => {
            setBuildParams({ task_run_item_ids: [] })
            setOpenBuild(false)
          }}
          onCancel={() => {
            setOpenBuild(false)
          }}
        />
      </ExDrawer>
    </>
  )
}

export default App
