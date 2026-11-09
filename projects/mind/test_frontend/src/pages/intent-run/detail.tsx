import CodeEditor from '@/components/CodeEditor'
import { formatDateTimeByString } from '@/utils/format'
import { Collapse, Descriptions, type CollapseProps, type DescriptionsProps } from 'antd'
import React, { useMemo } from 'react'

type Props = {
  record?: IntentRun
  defaultActiveKey?: string | string[]
  evalForm?: React.ReactNode
}

const App: React.FC<Props> = (props) => {
  const { record, defaultActiveKey = ['manual-eval', 'input', 'output'], evalForm } = props

  const descItems: DescriptionsProps['items'] = [
    {
      key: 'query',
      label: 'query',
      children: record?.input?.query,
      span: 2,
    },
    {
      key: 'intent_type',
      label: '意图类型',
      children: record?.output?.intent_type,
    },
    {
      key: 'total_time',
      label: '耗时',
      children: record?.total_time,
    },
    {
      key: 'creator',
      label: '创建人',
      children: record?.creator,
    },
    {
      key: 'created_time',
      label: '创建时间',
      children: formatDateTimeByString(record?.created_time),
    },
  ]

  const evalItems = useMemo(() => {
    const _items: DescriptionsProps['items'] = [
      { key: 'score', label: '评价得分', children: record?.manual_evaluation?.score, span: 2 },
      { key: 'comment', label: '评价意见', children: record?.manual_evaluation?.comment, span: 2 },
    ]

    record?.manual_evaluation?.metrics?.forEach((metric, index) => {
      _items.push(
        { key: `metric-value-${index}`, label: `${metric.name} 得分`, children: metric.value, span: 2 },
        { key: `metric-comment-${index}`, label: `${metric.name} 评价意见`, children: metric.comment, span: 2 }
      )
    })

    return _items
  }, [record])

  const items: CollapseProps['items'] = [
    {
      key: 'manual-eval',
      label: '人工评价',
      children: evalForm ? evalForm : <Descriptions items={evalItems} column={2} />,
    },
    {
      key: 'input',
      label: '输入信息',
      children: <CodeEditor value={record?.input} readOnly />,
    },
    {
      key: 'output',
      label: '输出信息',
      children: <CodeEditor value={record?.output} readOnly />,
    },
    {
      key: 'trajectory',
      label: '过程信息',
      children: <CodeEditor value={record?.trajectory} readOnly />,
    },
  ]

  return (
    <div>
      <Descriptions items={descItems} column={3} style={{ margin: 16 }} />
      <Collapse items={items} defaultActiveKey={defaultActiveKey} />
    </div>
  )
}

export default App
