import JsonViewRender from '@/components/JsonView'
import JsonViewText from '@/components/JsonView/text'
import MarkdownRenderer from '@/components/Markdown'
import { formatDateTimeByString, removeAuditFields } from '@/utils/format'
import { Button, Collapse, Descriptions, Spin, Tag, Typography, type CollapseProps, type DescriptionsProps } from 'antd'
import React, { useEffect, useMemo, useRef, useState } from 'react'

type Props = {
  record: TaskRunItem
  taskOptions: OptionItem[]
  taskRunOptions: OptionItem[]
  datasetItemOptions: OptionItem[]
}

const SHOW_TRACE_TYPES = ['react.tool_call.start', 'react.tool_results.done', 'react.text.done']

const MessageItem: React.FC<{ msg: TaskRunMessage }> = ({ msg }) => {
  const filteredTraces = (msg.traces || [])
    .filter((v) => SHOW_TRACE_TYPES.includes(v.type || ''))
    .map((v) => removeAuditFields(v, ['event_id']))

  const traceItems: CollapseProps['items'] = filteredTraces.length
    ? [{ key: 'traces', label: '查看 Trace', children: <JsonViewText value={filteredTraces} /> }]
    : []

  return (
    <div style={{ marginBottom: 8 }}>
      <Typography.Text strong>{msg.role}: </Typography.Text>
      <Typography.Text>{msg.content}</Typography.Text>
      {traceItems.length > 0 && <Collapse items={traceItems} size="small" style={{ marginTop: 4 }} />}
    </div>
  )
}

const App: React.FC<Props> = (props) => {
  const { record, taskOptions, taskRunOptions, datasetItemOptions } = props

  const taskRun = useMemo(
    () => taskRunOptions.find((item) => item.value === record?.task_run_id)?.data as TaskRun,
    [taskRunOptions, record?.task_run_id]
  )
  const task = useMemo(
    () => taskOptions.find((item) => item.value === taskRun?.task_id)?.data as Task,
    [taskOptions, taskRun?.task_id]
  )

  const datasetItem = datasetItemOptions.find((item) => item.value === record?.dataset_item_id)
    ?.data as ComplexReasoningCase

  const llmEval = record?.eval?.llm_evaluation
  const humanEval = record?.eval?.human_evaluation
  const videoObjectKey = (record?.metadata as Record<string, any> | undefined)?.video_object_key as string | undefined
  const logObjectKey = (record?.metadata as Record<string, any> | undefined)?.log_object_key as string | undefined
  const evidenceObjectKey = (record?.metadata as Record<string, any> | undefined)?.evidence_object_key as
    | string
    | undefined
  const evidenceMdObjectKey = (record?.metadata as Record<string, any> | undefined)?.evidence_md_object_key as
    | string
    | undefined
  // 预签名 URL：浏览器直连 TOS 流式播放，支持 Range/拖进度，不经过后端中转
  const [videoUrl, setVideoUrl] = useState('')
  const [videoLoading, setVideoLoading] = useState(false)
  const [videoError, setVideoError] = useState('')
  const videoRef = useRef<HTMLVideoElement>(null)
  // 记录用户设置的播放速度，切换 case 时保持不还原
  const [videoRate, setVideoRate] = useState(1)

  // 切换 case（videoUrl 变化）后，把用户之前设置的播放速度应用到新视频元素上
  useEffect(() => {
    const v = videoRef.current
    if (v && videoUrl) {
      v.playbackRate = videoRate
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoUrl])

  const fetchPresignedUrl = async (objectKey: string) => {
    const r = await fetch(`/api/file/presigned_url?object_key=${encodeURIComponent(objectKey)}`)
    const body = await r.json()
    if (!r.ok) {
      throw new Error(body?.message || body?.detail || `HTTP ${r.status}`)
    }
    if (!body?.data?.url) {
      throw new Error('返回数据缺少 data.url')
    }
    return body.data.url as string
  }

  useEffect(() => {
    if (!videoObjectKey) {
      setVideoUrl('')
      setVideoError('')
      setVideoLoading(false)
      return
    }
    setVideoLoading(true)
    setVideoError('')
    setVideoUrl('')
    fetchPresignedUrl(videoObjectKey)
      .then((url) => setVideoUrl(url))
      .catch((e: Error) => setVideoError(e.message || '未知错误'))
      .finally(() => setVideoLoading(false))
  }, [videoObjectKey])

  // 拉取文件内容（文本）：走 /api/file/download 接口
  const fetchFileText = async (objectKey: string): Promise<string> => {
    const r = await fetch(`/api/file/download/${encodeURIComponent(objectKey)}`)
    if (!r.ok) {
      throw new Error(`HTTP ${r.status}`)
    }
    return r.text()
  }

  // evidence_object_key：JSON 字符串
  const [evidenceContent, setEvidenceContent] = useState('')
  const [evidenceLoading, setEvidenceLoading] = useState(false)
  const [evidenceError, setEvidenceError] = useState('')

  useEffect(() => {
    if (!evidenceObjectKey) {
      setEvidenceContent('')
      setEvidenceError('')
      setEvidenceLoading(false)
      return
    }
    setEvidenceLoading(true)
    setEvidenceError('')
    setEvidenceContent('')
    fetchFileText(evidenceObjectKey)
      .then((text) => setEvidenceContent(text))
      .catch((e: Error) => setEvidenceError(e.message || '未知错误'))
      .finally(() => setEvidenceLoading(false))
  }, [evidenceObjectKey])

  // evidence_md_object_key：Markdown 文本
  const [evidenceMdContent, setEvidenceMdContent] = useState('')
  const [evidenceMdLoading, setEvidenceMdLoading] = useState(false)
  const [evidenceMdError, setEvidenceMdError] = useState('')

  useEffect(() => {
    if (!evidenceMdObjectKey) {
      setEvidenceMdContent('')
      setEvidenceMdError('')
      setEvidenceMdLoading(false)
      return
    }
    setEvidenceMdLoading(true)
    setEvidenceMdError('')
    setEvidenceMdContent('')
    fetchFileText(evidenceMdObjectKey)
      .then((text) => setEvidenceMdContent(text))
      .catch((e: Error) => setEvidenceMdError(e.message || '未知错误'))
      .finally(() => setEvidenceMdLoading(false))
  }, [evidenceMdObjectKey])

  // 下载文件：拉预签名 URL 后触发浏览器下载；失败降级走后端中转
  const handleDownload = async (objectKey: string, filename: string) => {
    try {
      const url = await fetchPresignedUrl(objectKey)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
    } catch {
      window.open(`/api/file/download/${objectKey}`, '_blank')
    }
  }

  const descItems: DescriptionsProps['items'] = [
    {
      key: 'task_id',
      label: '测试任务',
      children: task?.name || '',
      span: 2,
    },
    {
      key: 'case_id',
      label: '测试用例',
      children: datasetItem?.case_id || '',
      span: 2,
    },
    {
      key: 'status',
      label: '状态',
      children: record?.status || '',
    },
    {
      key: 'created_time',
      label: '执行时间',
      children: formatDateTimeByString(record?.created_time),
    },
    {
      key: 'llm_pass',
      label: '模型评价',
      children:
        llmEval?.is_pass != null ? (
          <Tag color={llmEval.is_pass ? 'success' : 'error'}>{llmEval.is_pass ? '通过' : '未通过'}</Tag>
        ) : (
          '—'
        ),
    },
    {
      key: 'human_pass',
      label: '人工评价',
      children:
        humanEval?.is_pass != null ? (
          <Tag color={humanEval.is_pass ? 'success' : 'error'}>{humanEval.is_pass ? '通过' : '未通过'}</Tag>
        ) : (
          '—'
        ),
    },
  ]

  // 按 session_id 分组 messages，保持顺序
  const sessionGroups = useMemo(() => {
    const messages = record?.messages || []
    const groups: Record<string, TaskRunMessage[]> = {}
    const order: string[] = []
    for (const msg of messages) {
      const sid = msg.session_id || 'default'
      if (!groups[sid]) {
        groups[sid] = []
        order.push(sid)
      }
      groups[sid].push(msg)
    }
    return order.map((sid, idx) => ({ sid, idx, messages: groups[sid] }))
  }, [record?.messages])

  const items: CollapseProps['items'] = useMemo(() => {
    const sessionItems = sessionGroups.map(({ sid, idx, messages }) => ({
      key: `session_${sid}`,
      label: `第${idx + 1}次对话记录`,
      children: (
        <div>
          {messages.map((msg) => (
            <MessageItem key={(msg._id as string) || `${msg.session_id}_${msg.role}_${msg.created_time}`} msg={msg} />
          ))}
        </div>
      ),
    }))

    return [
      ...(videoObjectKey
        ? [
            {
              key: 'video',
              label: '录制视频',
              children: videoLoading ? (
                <Spin tip="加载视频地址中..." />
              ) : videoUrl ? (
                <video
                  ref={videoRef}
                  src={videoUrl}
                  controls
                  style={{ width: '100%', maxHeight: 480, background: '#000' }}
                  onRateChange={() => {
                    if (videoRef.current) setVideoRate(videoRef.current.playbackRate)
                  }}
                />
              ) : (
                <Typography.Text type="danger">视频地址获取失败：{videoError}</Typography.Text>
              ),
            },
          ]
        : []),
      ...(logObjectKey
        ? [
            {
              key: 'log',
              label: (
                <span>
                  录制日志{' '}
                  <Button size="small" type="link" onClick={() => handleDownload(logObjectKey, 'logcat.log')}>
                    下载日志
                  </Button>
                </span>
              ),
              children: <Typography.Text type="secondary">点击「下载日志」下载 logcat.log</Typography.Text>,
            },
          ]
        : []),
      ...(evidenceObjectKey
        ? [
            {
              key: 'evidence',
              label: '证据信息 (JSON)',
              children: evidenceLoading ? (
                <Spin tip="加载中..." />
              ) : evidenceError ? (
                <Typography.Text type="danger">内容获取失败：{evidenceError}</Typography.Text>
              ) : (
                <JsonViewRender value={evidenceContent} />
              ),
            },
          ]
        : []),
      ...(evidenceMdObjectKey
        ? [
            {
              key: 'evidence_md',
              label: '证据信息 (Markdown)',
              children: evidenceMdLoading ? (
                <Spin tip="加载中..." />
              ) : evidenceMdError ? (
                <Typography.Text type="danger">内容获取失败：{evidenceMdError}</Typography.Text>
              ) : (
                <div style={{ padding: 12, background: '#fff', borderRadius: 6, border: '1px solid #f0f0f0' }}>
                  <MarkdownRenderer content={evidenceMdContent} />
                </div>
              ),
            },
          ]
        : []),
      {
        key: 'datasetItem',
        label: '测试用例信息',
        children: <JsonViewText value={removeAuditFields(datasetItem, ['dataset_id']) || {}} />,
      },
      ...sessionItems,
      {
        key: 'llm_evaluation',
        label: '模型评价',
        children: <JsonViewText value={record?.eval?.llm_evaluation || {}} />,
      },
      {
        key: 'human_evaluation',
        label: '人工评价',
        children: <JsonViewText value={record?.eval?.human_evaluation || {}} />,
      },
      {
        key: 'metadata',
        label: '元信息',
        children: <JsonViewText value={record?.metadata || {}} />,
      },
    ]
  }, [
    record,
    datasetItem,
    sessionGroups,
    videoObjectKey,
    videoUrl,
    videoLoading,
    videoError,
    logObjectKey,
    evidenceObjectKey,
    evidenceContent,
    evidenceLoading,
    evidenceError,
    evidenceMdObjectKey,
    evidenceMdContent,
    evidenceMdLoading,
    evidenceMdError,
  ])

  const defaultActiveKey = useMemo(() => (videoObjectKey ? ['video'] : ['llm_evaluation']), [videoObjectKey])

  return (
    <div>
      <Descriptions items={descItems} column={2} style={{ margin: 16 }} />
      <Collapse items={items} defaultActiveKey={defaultActiveKey} />
    </div>
  )
}

export default App
