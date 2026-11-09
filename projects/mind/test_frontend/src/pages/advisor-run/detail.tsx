import CodeEditor from '@/components/CodeEditor'
import { formatDateTimeByString } from '@/utils/format'
import { isJson } from '@/utils/json'
import { Collapse, Descriptions, type CollapseProps, type DescriptionsProps } from 'antd'
import React, { useMemo } from 'react'
import Markdown from '@/components/Markdown'

type Props = {
  record?: AdvisorRun
  defaultActiveKey?: string | string[]
  evalForm?: React.ReactNode
}

const jsonRender = (data?: string) => {
  if (!data) return <span></span>

  if (isJson(data)) return <CodeEditor value={data} readOnly />

  return <Markdown content={data} />
}

const App: React.FC<Props> = (props) => {
  const { record, defaultActiveKey = ['manual-eval', 'input', 'output'], evalForm } = props

  const descItems: DescriptionsProps['items'] = [
    {
      key: 'advise_type',
      label: '测试模块',
      children: record?.advise_type,
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

  const outItems: DescriptionsProps['items'] = [
    { key: 'advice', label: '建议', children: <div>{jsonRender(record?.output?.advice)}</div>, span: 2 },
    { key: 'reason', label: '原因', children: <div>{jsonRender(record?.output?.reason)}</div>, span: 2 },
    { key: 'think', label: '思考', children: <div>{jsonRender(record?.output?.think)}</div>, span: 2 },
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
      children: <Descriptions items={outItems} column={2} />,
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
