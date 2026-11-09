import MarkdownRenderer from '@/components/Markdown'
import React, { useEffect, useMemo, useState } from 'react'
import Api from '@/apis/task-data'

type Props = {
  record: TaskRun
}

interface MetaData {
  total_case_num: number
  passed_case_num: number
  pass_rate: number
  tags_correct_number_and_rate?: Record<string, { passed_number: number; pass_rate: number; tag_total: number }>
  result?: string
  [key: string]: unknown
}

const App: React.FC<Props> = (props) => {
  const { record } = props
  const [loading, setLoading] = useState(false)
  const [metadata, setMetadata] = useState<MetaData | undefined>()

  const report = useMemo(() => {
    if (metadata?.error) return `**执行错误：** ${metadata.error}`

    const tagsLines = metadata?.tags_correct_number_and_rate
      ? Object.entries(metadata.tags_correct_number_and_rate)
          .map(
            ([tag, result]) =>
              `- **${tag}** - 总数：${result.tag_total}，正确数：${result.passed_number}，通过率：${(+result.pass_rate * 100).toFixed(2)}%`
          )
          .join('\n')
      : ''

    const { time_avg, time_p50, time_p90, time_p99 } = (metadata || {}) as {
      time_avg?: number
      time_p50?: number
      time_p90?: number
      time_p99?: number
    }

    const md = [
      `**测试用例总数：** ${metadata?.total_case_num ?? '-'}`,
      `**通过的测试用例数：** ${metadata?.passed_case_num ?? '-'}`,
      `**测试用例通过率：** ${+((metadata?.pass_rate ?? 0) * 100).toFixed(2)}%`,
      `**标签正确数和通过率：**`,
      tagsLines,
      `**平均耗时：** ${time_avg ? `${time_avg.toFixed(2)}ms` : '-'}`,
      `**P50耗时：** ${time_p50 ? `${time_p50.toFixed(2)}ms` : '-'}`,
      `**P90耗时：** ${time_p90 ? `${time_p90.toFixed(2)}ms` : '-'}`,
      `**P99耗时：** ${time_p99 ? `${time_p99.toFixed(2)}ms` : '-'}`,
    ]
      .filter(Boolean)
      .join('\n\n')

    return md
  }, [metadata])

  useEffect(() => {
    setLoading(true)
    Api.taskRun
      .get(record.id as string)
      .then((res) => {
        setMetadata(res.metadata as MetaData)
      })
      .finally(() => setLoading(false))
  }, [record])

  return <>{loading ? <p>加载中...</p> : <MarkdownRenderer content={report} />}</>
}

export default App
