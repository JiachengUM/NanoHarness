import { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Form, Input, InputNumber, Modal, Popconfirm, Progress, Select, Space, Steps, Table, Tag, Tree, Upload, message } from 'antd'
import type { TableColumnsType, UploadFile } from 'antd'
import type { DataNode } from 'antd/es/tree'
import type { RcFile } from 'antd/es/upload/interface'
import { CloseOutlined, EyeOutlined, UploadOutlined } from '@ant-design/icons'
import Api from '@/apis/data-generation'
import TagListInput from '@/components/Form/tag-list-input'
import JsonViewText from '@/components/JsonView/text'
import TaskForm from '@/pages/data-generation/task/form'
import { getLeafTagNamesFromTree } from '@/utils/tag-tree-leaf'
import { normalizeScenarioPlan, useGeneration } from '@/context/generationContext'

type TagTreeUploadForm = {
  name: string
  description?: string
}

type PlanQueryForm = {
  taskId: string
  tagTreeName: string
  query: string
}

type PlanEditForm = Pick<
  ScenarioPlan,
  'task_description' | 'target_tags' | 'interpretation_notes'
>

type ScenarioForm = Pick<GenerationScenario, 'scenario_id' | 'scenario_name' | 'description' | 'tags'>

type CaseForm = {
  datasetId: string
  casesPerScenario: number
}

const toPlanFormValues = (rawPlan: ScenarioPlan): PlanEditForm => ({
  task_description: rawPlan.task_description || '',
  target_tags: rawPlan.target_tags || [],
  interpretation_notes: rawPlan.interpretation_notes || '',
})

const QUERY_EXAMPLES = `例如：
帮我生成空调温度增减控制的场景
帮我生成先说过自己住在哪儿，然后在新的对话中导航回家的场景
帮我生成各种结合了导航、车控和联网搜索的场景
帮我生成各种可能危及行车安全的车控语音操作的场景`

const WORKFLOW_STEP_ALERTS: Record<number, { message: string; description: string }> = {
  0: {
    message: '描述需求生成计划',
    description: '选择或新建合成任务和测试维度，输入数据合成需求；生成计划后可在本页核对并修改计划。',
  },
  1: {
    message: '生成场景和用例',
    description: '根据已确认的计划生成并管理场景；场景生成过程中或生成后，可选择已有场景继续生成并保存用例。',
  },
}

const clampProgressPercent = (value?: number) => Math.max(0, Math.min(value || 0, 100))

type TagTreeNodeRaw = {
  name: string
  children?: TagTreeNodeRaw[]
}

type TreeNodeWithCount = {
  leafCount: number
  node: DataNode
}

const countAndConvertNode = (node: TagTreeNodeRaw, keyPrefix = '0'): TreeNodeWithCount => {
  const isLeaf = !node.children?.length
  if (isLeaf) {
    return {
      leafCount: 1,
      node: {
        key: keyPrefix,
        title: <Tag color="blue">{node.name}</Tag>,
      },
    }
  }

  let totalLeaves = 0
  const children: DataNode[] = []
  node.children?.forEach((child, index) => {
    const result = countAndConvertNode(child, `${keyPrefix}-${index}`)
    totalLeaves += result.leafCount
    children.push(result.node)
  })

  return {
    leafCount: totalLeaves,
    node: {
      key: keyPrefix,
      title: (
        <Space size={4}>
          <span>{node.name}</span>
          <Tag color="default" style={{ fontSize: 12 }}>{totalLeaves} 个叶子</Tag>
        </Space>
      ),
      children,
    },
  }
}

const CaseGenerationPage: React.FC = () => {
  // 从 Context 获取生成相关的全局状态（在路由切换时持久化）
  const {
    currentStep,
    setCurrentStep,
    plan,
    setPlan,
    scenarios,
    setScenarios,
    progress,
    setProgress,
    generatingScenarios,
    selectedScenarioIds,
    setSelectedScenarioIds,
    scenarioGenerationStopped,
    caseProgress,
    setCaseProgress,
    result,
    setResult,
    formSelections,
    setFormSelections,
    datasets,
    setDatasets,
    generateScenarios: generateScenariosFromContext,
    stopScenarioGeneration,
    refreshScenarios,
    caseGenerationAbortRef,
  } = useGeneration()

  const [queryForm] = Form.useForm<PlanQueryForm>()
  const [planForm] = Form.useForm<PlanEditForm>()
  const [scenarioForm] = Form.useForm<ScenarioForm>()
  const [caseForm] = Form.useForm<CaseForm>()
  const [datasetForm] = Form.useForm<ComplexReasoningDataset>()
  const [tagTreeForm] = Form.useForm<TagTreeUploadForm>()

  // 本页 UI 状态（路由切换时无需持久化）
  const [tasks, setTasks] = useState<GenerationTask[]>([])
  const [tagTrees, setTagTrees] = useState<TagTreeBrief[]>([])
  const [planning, setPlanning] = useState(false)
  const [generatingCases, setGeneratingCases] = useState(false)
  const [datasetOpen, setDatasetOpen] = useState(false)
  const [taskOpen, setTaskOpen] = useState(false)
  const [tagTreeOpen, setTagTreeOpen] = useState(false)
  const [tagTreeSubmitting, setTagTreeSubmitting] = useState(false)
  const [tagTreeFile, setTagTreeFile] = useState<RcFile>()
  const [scenarioOpen, setScenarioOpen] = useState(false)
  const [editingScenario, setEditingScenario] = useState<GenerationScenario>()
  const [leafTagNames, setLeafTagNames] = useState<string[]>([])
  const [leafTagsLoading, setLeafTagsLoading] = useState(false)
  const [scenarioPagination, setScenarioPagination] = useState({ current: 1, pageSize: 10 })
  const [casePagination, setCasePagination] = useState({ current: 1, pageSize: 10 })
  const [previewTreeOpen, setPreviewTreeOpen] = useState(false)
  const [previewTreeData, setPreviewTreeData] = useState<DataNode[]>([])
  const [previewTreeName, setPreviewTreeName] = useState('')
  const [previewTreeLoading, setPreviewTreeLoading] = useState(false)
  const [previewTotalLeaves, setPreviewTotalLeaves] = useState(0)

  const selectedTaskId = Form.useWatch('taskId', queryForm)
  const selectedTagTreeName = Form.useWatch('tagTreeName', queryForm)
  const effectiveTaskId = selectedTaskId || plan?.task_id
  const effectiveTagTreeName = selectedTagTreeName || plan?.tag_tree_name

  const loadDatasets = () => Api.dataset.list().then(setDatasets)

  const loadTasks = async () => {
    const items = await Api.generationTask.list()
    setTasks(items)
    return items
  }

  const loadTagTrees = async () => {
    const items = await Api.tagTree.list()
    setTagTrees(items)
    return items
  }

  // 初次挂载：加载下拉选项数据；并从 Context 恢复表单值
  useEffect(() => {
    let cancelled = false
    const init = async () => {
      await loadTasks()
      if (cancelled) return
      await loadTagTrees()
      if (cancelled) return
      await loadDatasets()
      if (cancelled) return
      // 从 Context 恢复表单选择
      if (formSelections.taskId) {
        queryForm.setFieldValue('taskId', formSelections.taskId)
      }
      if (formSelections.tagTreeName) {
        queryForm.setFieldValue('tagTreeName', formSelections.tagTreeName)
      }
      if (formSelections.query) {
        queryForm.setFieldValue('query', formSelections.query)
      }
    }
    init()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 表单字段变化时同步回 Context（仅在有值时同步，避免页面重新挂载时 watch 初始值为空覆盖已选内容）
  useEffect(() => {
    if (selectedTaskId) {
      setFormSelections((prev) => ({ ...prev, taskId: selectedTaskId }))
    }
  }, [selectedTaskId, setFormSelections])

  useEffect(() => {
    if (selectedTagTreeName) {
      setFormSelections((prev) => ({ ...prev, tagTreeName: selectedTagTreeName }))
    }
  }, [selectedTagTreeName, setFormSelections])

  const handleTaskCreated = async (values?: GenerationTask) => {
    const items = await loadTasks()
    const created = values?.name
      ? items.find((task) => task.name === values.name)
      : undefined
    if (created?.id) {
      queryForm.setFieldValue('taskId', created.id)
    }
    setTaskOpen(false)
  }

  const closeTagTreeForm = () => {
    setTagTreeOpen(false)
    setTagTreeFile(undefined)
    tagTreeForm.resetFields()
  }

  const previewSelectedTagTree = async () => {
    const tagTreeName = selectedTagTreeName
    if (!tagTreeName) {
      message.info('请先选择一个测试维度')
      return
    }
    const tagTree = tagTrees.find((t) => t.name === tagTreeName)
    if (!tagTree?.id) {
      message.error('找不到该测试维度')
      return
    }
    setPreviewTreeLoading(true)
    setPreviewTreeName(tagTreeName)
    setPreviewTreeOpen(true)
    try {
      const detail = await Api.tagTree.detail(tagTree.id)
      const treeData = detail.tree as { root?: TagTreeNodeRaw }
      if (treeData?.root) {
        const result = countAndConvertNode(treeData.root, '0')
        setPreviewTreeData([result.node])
        setPreviewTotalLeaves(result.leafCount)
      } else {
        setPreviewTreeData([])
        setPreviewTotalLeaves(0)
      }
    } catch {
      message.error('加载测试维度失败')
    } finally {
      setPreviewTreeLoading(false)
    }
  }

  const createTagTree = async () => {
    const values = await tagTreeForm.validateFields()
    if (!tagTreeFile) {
      message.error('请选择标签树 JSON 文件')
      return
    }

    setTagTreeSubmitting(true)
    try {
      const tree = JSON.parse(await tagTreeFile.text())
      const created = await Api.tagTree.create({ ...values, tree })
      message.success('测试维度创建成功')
      closeTagTreeForm()
      await loadTagTrees()
      queryForm.setFieldValue('tagTreeName', created.name || values.name)
    } catch (error) {
      if (error instanceof SyntaxError) message.error('JSON 文件格式不正确')
    } finally {
      setTagTreeSubmitting(false)
    }
  }

  const taskOptions = useMemo(
    () => tasks.map((task) => ({ label: task.name || task.id, value: task.id })),
    [tasks]
  )

  const tagTreeOptions = useMemo(
    () => tagTrees.map((tree) => ({ label: tree.name, value: tree.name })),
    [tagTrees]
  )

  const datasetOptions = useMemo(
    () => datasets.map((dataset) => ({
      label: dataset.item_count === undefined || dataset.item_count === null
        ? dataset.name
        : `${dataset.name}（${dataset.item_count} 条）`,
      value: dataset.id,
    })),
    [datasets]
  )

  const selectedTagTree = useMemo(
    () => tagTrees.find((tree) => tree.name === effectiveTagTreeName),
    [effectiveTagTreeName, tagTrees]
  )

  useEffect(() => {
    if (!plan || !selectedTagTree?.id) {
      setLeafTagNames([])
      return
    }

    let cancelled = false
    setLeafTagsLoading(true)
    Api.tagTree.detail(selectedTagTree.id)
      .then((detail) => {
        if (!cancelled) setLeafTagNames(getLeafTagNamesFromTree(detail.tree))
      })
      .finally(() => {
        if (!cancelled) setLeafTagsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [plan, selectedTagTree?.id])

  const hasScenarioGenerationStarted = generatingScenarios || !!progress || scenarios.length > 0

  const canGoToStep = (step: number) => {
    if (step === 0) return true
    if (step === 1) return !!plan || hasScenarioGenerationStarted
    return false
  }

  const selectAllScenarios = useCallback(() => {
    setSelectedScenarioIds(scenarios.map((scenario) => scenario.scenario_id))
  }, [scenarios, setSelectedScenarioIds])

  const goToStep = (step: number) => {
    if (!canGoToStep(step)) return
    if (step === 1 && scenarios.length > 0) {
      selectAllScenarios()
    }
    setCurrentStep(step)
  }

  const stepItems = [
    { title: '描述需求生成计划' },
    { title: '生成场景和用例', disabled: !canGoToStep(1) },
  ]

  const planFormValues = useMemo(
    () => (plan ? toPlanFormValues(plan) : undefined),
    [plan]
  )

  const isPlanEditable = !!plan?.task_description && !!plan.target_tags?.length && !!plan.interpretation_notes

  const openPlan = (nextPlan: ScenarioPlan) => {
    const normalized = normalizeScenarioPlan(nextPlan as any)
    setPlan(normalized)
    setCurrentStep(0)
  }

  useEffect(() => {
    if (!plan) return
    planForm.setFieldsValue(toPlanFormValues(plan))
  }, [plan, planForm])

  const generatePlan = async () => {
    const values = await queryForm.validateFields()
    // 同步 query 到 Context
    setFormSelections((prev) => ({ ...prev, query: values.query }))
    setPlanning(true)
    try {
      const nextPlan = await Api.scenarioPlan.generate({
        query: values.query,
        tag_tree_name: values.tagTreeName,
        task_id: values.taskId,
      })
      message.success('场景生成计划已生成')
      // 重置场景相关状态（保留 plan 之外清空）
      setScenarios([])
      setSelectedScenarioIds([])
      setProgress(undefined)
      setCaseProgress(undefined)
      setResult(undefined)
      openPlan(nextPlan)
    } finally {
      setPlanning(false)
    }
  }

  const savePlan = async (status?: ScenarioPlanStatus) => {
    if (!plan?.id) {
      message.error('当前场景生成计划缺少 id，无法保存。请重新生成计划或检查后端响应是否返回 id。')
      return
    }
    const values = await planForm.validateFields()
    const normalizedValues = {
      ...values,
      target_tags: values.target_tags.map((tag) => tag.trim()).filter(Boolean),
    }
    const nextPlan = await Api.scenarioPlan.update(plan.id, {
      ...normalizedValues,
      ...(status ? { status } : {}),
    })
    setPlan(normalizeScenarioPlan(nextPlan as any))
    message.success('场景生成计划已保存')
    return nextPlan
  }

  const generateScenarios = async () => {
    if (!plan?.id) {
      message.error('当前场景生成计划缺少 id，无法生成场景。请重新生成计划或检查后端响应是否返回 id。')
      return
    }
    if (!effectiveTaskId) {
      message.error('当前场景生成计划缺少生成任务 id，无法生成场景。')
      return
    }

    const savedPlan = await savePlan('confirmed')
    if (!savedPlan) return

    setCurrentStep(1)
    // 通过 Context 发起 SSE 生成（SSE 连接由 Provider 持有，不受路由切换影响）
    await generateScenariosFromContext(plan.id)
  }

  const generateCases = async () => {
    if (!effectiveTagTreeName) return
    if (!selectedScenarioIds.length) {
      message.error('请至少选择一个场景')
      return
    }
    const values = await caseForm.validateFields()
    setGeneratingCases(true)
    setCaseProgress(undefined)
    setResult({
      cases: [],
      totalGenerated: 0,
    })

    const caseAbortController = new AbortController()
    // 附带取消数据，供 Provider 在 beforeunload 时通过 sendBeacon 通知后端
    ;(caseAbortController as any).cancelData = { datasetId: values.datasetId }
    caseGenerationAbortRef.current = caseAbortController

    try {
      await Api.caseGeneration.generateStream(
        {
          scenarioIds: selectedScenarioIds,
          datasetId: values.datasetId,
          casesPerScenario: values.casesPerScenario,
          tagTreeName: effectiveTagTreeName,
        },
        (event) => {
          if (event.type === 'progress') {
            setCaseProgress(event.data)
          }

          if (event.type === 'case') {
            setResult((prev) => {
              const previousCases = prev?.cases || []
              if (previousCases.some((item) => item.case_id === event.data.caseItem.case_id)) return prev

              const cases = [...previousCases, event.data.caseItem]
              return {
                cases,
                totalGenerated: cases.length,
                errors: prev?.errors,
              }
            })
          }

          if (event.type === 'error') {
            if (event.data.code !== 'GENERATION_CANCELLED') {
              message.error(event.data.message)
            }
          }

          if (event.type === 'complete') {
            setCaseProgress({
              stage: 'completed',
              current: event.data.totalGenerated,
              total: event.data.totalScenarios * event.data.casesPerScenario,
              progressPercentage: 100,
              currentStep: '用例生成完成',
            })
            setResult((prev) => ({
              cases: prev?.cases || [],
              totalGenerated: event.data.totalGenerated,
              errors: prev?.errors,
            }))
            message.success(`成功生成并保存 ${event.data.totalGenerated} 个用例`)
          }
        },
        undefined,
        caseAbortController.signal
      )
      loadDatasets()
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        message.info('用例生成已终止')
      } else {
        throw error
      }
    } finally {
      caseGenerationAbortRef.current = null
      setGeneratingCases(false)
    }
  }

  const stopCaseGeneration = async () => {
    const datasetId = caseForm.getFieldValue('datasetId')
    if (datasetId) {
      try {
        await Api.caseGeneration.cancelGeneration({ datasetId })
      } catch {
        // 请求取消失败时，仍然执行前端断流
      }
    }
    caseGenerationAbortRef.current?.abort()
  }

  const createDataset = async () => {
    const values = await datasetForm.validateFields()
    const dataset = await Api.dataset.create(values)
    message.success('本地数据集创建成功')
    setDatasetOpen(false)
    datasetForm.resetFields()
    await loadDatasets()
    caseForm.setFieldValue('datasetId', dataset.id)
  }

  const openEditScenario = (record: GenerationScenario) => {
    setEditingScenario(record)
    scenarioForm.setFieldsValue({
      scenario_id: record.scenario_id,
      scenario_name: record.scenario_name,
      description: record.description,
      tags: record.tags || [],
    })
    setScenarioOpen(true)
  }

  const openCopyScenario = (record: GenerationScenario) => {
    setEditingScenario(undefined)
    scenarioForm.setFieldsValue({
      scenario_id: `${record.scenario_id}-copy`,
      scenario_name: `${record.scenario_name}-副本`,
      description: record.description,
      tags: record.tags || [],
    })
    setScenarioOpen(true)
  }

  const closeScenarioForm = () => {
    setScenarioOpen(false)
    setEditingScenario(undefined)
    scenarioForm.resetFields()
  }

  const saveScenario = async () => {
    if (!effectiveTaskId) {
      message.warning('请先选择生成任务')
      return
    }
    const values = await scenarioForm.validateFields()

    if (editingScenario?.id) {
      await Api.scenario.update({
        ...editingScenario,
        ...values,
      })
      message.success('场景已更新')
    } else {
      await Api.scenario.create({
        ...values,
        generation_task_id: effectiveTaskId,
        tag_tree_id: selectedTagTree?.id,
        source_query: queryForm.getFieldValue('query'),
      } as GenerationScenario)
      message.success('场景已新增')
    }

    closeScenarioForm()
    await refreshScenarios(effectiveTaskId)
  }

  const deleteScenario = async (record: GenerationScenario) => {
    if (!record.id) return
    await Api.scenario.del(record.id)
    message.success('场景已删除')
    await refreshScenarios(effectiveTaskId!)
  }

  const scenarioSelectionColumns: TableColumnsType<GenerationScenario> = [
    { title: '场景 ID', dataIndex: 'scenario_id', width: 180 },
    { title: '场景名称', dataIndex: 'scenario_name', width: 200 },
    { title: '描述', dataIndex: 'description', ellipsis: true },
    {
      title: '标签',
      dataIndex: 'tags',
      width: 260,
      render: (tags: string[]) => tags?.map((tag) => <Tag key={tag}>{tag}</Tag>),
    },
  ]

  const scenarioColumns: TableColumnsType<GenerationScenario> = [
    ...scenarioSelectionColumns,
    {
      title: '操作',
      width: 180,
      fixed: 'right',
      render: (_, record) => (
        <Space>
          <a onClick={() => openCopyScenario(record)}>复制</a>
          <a onClick={() => openEditScenario(record)}>编辑</a>
          <Popconfirm title="确认删除该场景？" onConfirm={() => deleteScenario(record)}>
            <a>删除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const caseColumns: TableColumnsType<GeneratedCase> = [
    { title: 'Case ID', dataIndex: 'case_id', width: 220 },
    { title: '来源场景', dataIndex: 'source_scenario_name', width: 180 },
    {
      title: '标签',
      dataIndex: 'tags',
      width: 260,
      render: (tags: string[]) => tags?.map((tag) => <Tag key={tag}>{tag}</Tag>),
    },
    {
      title: '内容',
      render: (_, record) => <JsonViewText value={record} />,
    },
  ]

  const renderStepContent = () => {
    if (currentStep === 0) {
      return (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Card title="1. 选择任务和测试维度，输入数据合成需求">
            <Form form={queryForm} layout="vertical">
              <Form.Item label="合成任务" required>
                <Space.Compact style={{ width: '100%' }}>
                  <Form.Item name="taskId" noStyle rules={[{ required: true, message: '请选择或新建生成任务' }]}>
                    <Select options={taskOptions} showSearch allowClear placeholder="选择已有任务" style={{ width: '100%' }} />
                  </Form.Item>
                  <Button onClick={() => setTaskOpen(true)}>新建任务</Button>
                </Space.Compact>
              </Form.Item>
              <Form.Item label="测试维度" required>
                <Space.Compact style={{ width: '100%' }}>
                  <Form.Item name="tagTreeName" noStyle rules={[{ required: true, message: '请选择或新建测试维度' }]}>
                    <Select options={tagTreeOptions} showSearch allowClear placeholder="选择已有测试维度" style={{ width: '100%' }} />
                  </Form.Item>
                  <Button
                    icon={<EyeOutlined />}
                    onClick={previewSelectedTagTree}
                    disabled={!selectedTagTreeName}
                  >
                    预览
                  </Button>
                  <Button onClick={() => setTagTreeOpen(true)}>新建测试维度</Button>
                </Space.Compact>
              </Form.Item>
              <Form.Item
                label="描述你想要合成什么场景的数据"
                name="query"
                rules={[{ required: true, message: '请输入场景描述' }]}
                extra={<div style={{ color: 'rgba(0, 0, 0, 0.45)', whiteSpace: 'pre-line' }}>{QUERY_EXAMPLES}</div>}
              >
                <Input.TextArea rows={5} placeholder="请输入场景描述，可参考下方示例" />
              </Form.Item>
              <Space>
                <Button type="primary" loading={planning} onClick={generatePlan}>
                  {planning ? '生成场景生成计划...约需10秒' : plan ? '重新生成场景计划' : '生成场景计划'}
                </Button>
              </Space>
            </Form>
          </Card>

          {plan && (
            <Card title="2. 查看并编辑场景生成计划">
              {!isPlanEditable && (
                <Alert
                  type="warning"
                  showIcon
                  style={{ marginBottom: 16 }}
                  message="场景生成计划字段不完整"
                  description="后端已返回 Plan，但缺少改写后的详细任务描述、覆盖的测试维度或 LLM 理解说明。请检查 /scenario-planning/generate 的响应数据。"
                />
              )}
              <Form key={plan.id} form={planForm} layout="vertical" initialValues={planFormValues}>
                <Form.Item label="改写后的详细任务描述" name="task_description" rules={[{ required: true }]}>
                  <Input.TextArea rows={4} />
                </Form.Item>
                <Form.Item
                  label="覆盖的测试维度"
                  name="target_tags"
                  rules={[
                    { required: true, type: 'array' },
                    {
                      validator: (_, tags: string[]) => {
                        const normalized = (tags || []).map((tag) => tag.trim()).filter(Boolean)
                        if (!normalized.length) {
                          return Promise.reject(new Error('请至少添加一个测试维度'))
                        }
                        if (!leafTagNames.length) return Promise.resolve()
                        const invalid = normalized.filter((tag) => !leafTagNames.includes(tag))
                        if (!invalid.length) return Promise.resolve()
                        const preview = invalid.slice(0, 5).join('、')
                        const suffix = invalid.length > 5 ? ' 等' : ''
                        return Promise.reject(new Error(`以下标签不在测试维度叶子节点中：${preview}${suffix}`))
                      },
                    },
                  ]}
                >
                  <TagListInput
                    placeholder="暂未选择测试维度，请点击下方按钮添加"
                    leafTagOptions={leafTagNames}
                    leafTagsLoading={leafTagsLoading}
                  />
                </Form.Item>
                <Form.Item label="LLM 对描述性文本的理解" name="interpretation_notes" rules={[{ required: true }]}>
                  <Input.TextArea rows={4} />
                </Form.Item>
                <Button type="primary" loading={generatingScenarios} onClick={generateScenarios}>
                  开始生成场景
                </Button>
              </Form>
            </Card>
          )}
        </Space>
      )
    }

    if (currentStep === 1) {
      return (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Card title="3. 生成并管理场景">
            {scenarioGenerationStopped && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 12 }}
                message="场景生成流程已终止"
                description="你可以继续编辑/删除已有场景，或回到第一页重新点击“开始生成场景”发起新一轮生成。"
              />
            )}
            {progress && (
              <Space direction="vertical" style={{ width: '100%', marginBottom: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <span>当前步骤：{progress.currentStep || progress.stage || '生成场景'}</span>
                    <span>生成进度：{clampProgressPercent(progress.progressPercentage)}%</span>
                  </div>
                  {generatingScenarios && (
                    <Button
                      size="small"
                      type="text"
                      danger
                      icon={<CloseOutlined />}
                      onClick={stopScenarioGeneration}
                      title="终止场景生成"
                    />
                  )}
                </div>
                <Progress percent={clampProgressPercent(progress.progressPercentage)} />
              </Space>
            )}
            <Space wrap style={{ marginBottom: 12 }}>
              <Button size="small" onClick={selectAllScenarios} disabled={!scenarios.length}>
                全选用于生成用例
              </Button>
              <Button size="small" onClick={() => setSelectedScenarioIds([])} disabled={!selectedScenarioIds.length}>
                取消全选
              </Button>
              <span style={{ color: 'rgba(0, 0, 0, 0.45)' }}>
                已选 {selectedScenarioIds.length} / 共 {scenarios.length}
              </span>
            </Space>
            <Table
              rowKey={(record) => record.scenario_id}
              columns={scenarioColumns}
              dataSource={scenarios}
              pagination={{
                ...scenarioPagination,
                total: scenarios.length,
                showSizeChanger: true,
                showQuickJumper: true,
                showTotal: (total) => `共 ${total} 条`,
                pageSizeOptions: ['10', '20', '50', '100'],
                onChange: (page, pageSize) => {
                  setScenarioPagination({ current: page, pageSize })
                },
              }}
              scroll={{ x: 1100 }}
              rowSelection={{
                selectedRowKeys: selectedScenarioIds,
                onChange: (keys) => setSelectedScenarioIds(keys as string[]),
              }}
            />
          </Card>

          <Card title="4. 基于场景生成用例">
            {!scenarios.length && (
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                message="暂无可生成用例的场景"
                description="请等待场景生成产生结果后再生成用例。"
              />
            )}
            <Form form={caseForm} layout="vertical" initialValues={{ casesPerScenario: 1 }}>
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                message={`将基于上方表格中选中的 ${selectedScenarioIds.length} 个场景生成用例`}
                description="如需调整范围，请直接在上方场景表格左侧勾选或取消勾选。"
              />
              <Form.Item label="Platform 本地数据集" required>
                <Space.Compact style={{ width: '100%' }}>
                  <Form.Item name="datasetId" noStyle rules={[{ required: true }]}>
                    <Select options={datasetOptions} showSearch allowClear placeholder="选择数据集" style={{ width: '100%' }} />
                  </Form.Item>
                  <Button onClick={() => setDatasetOpen(true)}>新建数据集</Button>
                </Space.Compact>
              </Form.Item>
              <Form.Item label="每个场景生成用例数" name="casesPerScenario" rules={[{ required: true }]}>
                <InputNumber min={1} max={20} />
              </Form.Item>
              <Button type="primary" loading={generatingCases} disabled={!scenarios.length} onClick={generateCases}>
                生成并保存用例
              </Button>
            </Form>
            {caseProgress && (
              <Space direction="vertical" style={{ width: '100%', marginTop: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <span>当前步骤：{caseProgress.currentStep || caseProgress.stage || '生成用例'}</span>
                    <span>生成进度：{clampProgressPercent(caseProgress.progressPercentage)}%</span>
                  </div>
                  {generatingCases && (
                    <Button
                      size="small"
                      type="text"
                      danger
                      icon={<CloseOutlined />}
                      onClick={stopCaseGeneration}
                      title="终止用例生成"
                    />
                  )}
                </div>
                <Progress percent={clampProgressPercent(caseProgress.progressPercentage)} />
              </Space>
            )}
          </Card>

          {result && (
            <Card title={`用例生成结果：成功 ${result.totalGenerated} 条`}>
              {!!result.errors?.length && (
                <div style={{ marginBottom: 16, color: '#cf1322' }}>
                  {result.errors.map((error, index) => (
                    <div key={`${error.scenarioId}-${index}`}>{error.scenarioId}: {error.error}</div>
                  ))}
                </div>
              )}
              <Table
                rowKey={(record) => record.id || record.case_id || `${record.source_scenario_id}-${record.source_scenario_name}`}
                columns={caseColumns}
                dataSource={result.cases}
                pagination={{
                  ...casePagination,
                  total: result.cases.length,
                  showSizeChanger: true,
                  showQuickJumper: true,
                  showTotal: (total) => `共 ${total} 条`,
                  pageSizeOptions: ['10', '20', '50', '100'],
                  onChange: (page, pageSize) => {
                    setCasePagination({ current: page, pageSize })
                  },
                }}
                scroll={{ x: 1200 }}
              />
            </Card>
          )}
        </Space>
      )
    }

    return null
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message={WORKFLOW_STEP_ALERTS[currentStep]?.message ?? WORKFLOW_STEP_ALERTS[0].message}
        description={WORKFLOW_STEP_ALERTS[currentStep]?.description ?? WORKFLOW_STEP_ALERTS[0].description}
      />

      <Steps
        current={currentStep}
        items={stepItems}
        onChange={goToStep}
      />

      {renderStepContent()}

      <Modal
        title="新建生成任务"
        open={taskOpen}
        onCancel={() => setTaskOpen(false)}
        footer={null}
        destroyOnHidden
      >
        <TaskForm onCancel={() => setTaskOpen(false)} onSuccess={handleTaskCreated} />
      </Modal>

      <Modal
        title="新建测试维度"
        open={tagTreeOpen}
        confirmLoading={tagTreeSubmitting}
        onCancel={closeTagTreeForm}
        onOk={createTagTree}
        destroyOnHidden
      >
        <Form form={tagTreeForm} layout="vertical">
          <Form.Item label="名称" name="name" rules={[{ required: true, message: '请输入名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item label="描述" name="description">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item label="标签树 JSON" required>
            <Upload
              accept=".json"
              maxCount={1}
              fileList={
                tagTreeFile
                  ? [{
                      uid: tagTreeFile.uid,
                      name: tagTreeFile.name,
                      status: 'done',
                      originFileObj: tagTreeFile,
                    } satisfies UploadFile]
                  : []
              }
              beforeUpload={(nextFile) => {
                setTagTreeFile(nextFile)
                return false
              }}
              onRemove={() => setTagTreeFile(undefined)}
            >
              <Button icon={<UploadOutlined />}>选择文件</Button>
            </Upload>
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="新建 Platform 本地数据集" open={datasetOpen} onCancel={() => setDatasetOpen(false)} onOk={createDataset}>
        <Form form={datasetForm} layout="vertical">
          <Form.Item label="数据集名称" name="name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item label="描述" name="description">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`测试维度预览：${previewTreeName}`}
        open={previewTreeOpen}
        onCancel={() => setPreviewTreeOpen(false)}
        footer={null}
        width={700}
        destroyOnHidden
      >
        {previewTreeLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>加载中...</div>
        ) : previewTreeData.length > 0 ? (
          <>
            <Alert
              style={{ marginBottom: 12 }}
              type="info"
              showIcon
              message={`共 ${previewTotalLeaves} 个叶子标签`}
            />
            <div style={{ maxHeight: 450, overflow: 'auto', padding: '8px 0', border: '1px solid #f0f0f0', borderRadius: 4 }}>
              <Tree
                treeData={previewTreeData}
                defaultExpandAll
                selectable={false}
                showLine={{ showLeafIcon: false }}
              />
            </div>
          </>
        ) : (
          <div style={{ textAlign: 'center', color: 'rgba(0, 0, 0, 0.45)', padding: 40 }}>暂无数据</div>
        )}
        <div style={{ marginTop: 12, color: 'rgba(0, 0, 0, 0.45)', fontSize: 12 }}>
          提示：蓝色标签为可用于场景标记的叶子节点（最终测试维度）
        </div>
      </Modal>

      <Modal
        title={editingScenario ? '编辑场景' : '新增场景'}
        open={scenarioOpen}
        onCancel={closeScenarioForm}
        onOk={saveScenario}
        width={720}
      >
        <Form form={scenarioForm} layout="vertical">
          <Form.Item label="场景 ID" name="scenario_id" rules={[{ required: true, message: '请输入场景 ID' }]}>
            <Input placeholder="例如：scenario_001" />
          </Form.Item>
          <Form.Item label="场景名称" name="scenario_name" rules={[{ required: true, message: '请输入场景名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item label="描述" name="description" rules={[{ required: true, message: '请输入场景描述' }]}>
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item label="标签" name="tags" rules={[{ required: true, type: 'array', min: 1, message: '请至少输入一个标签' }]}>
            <Select mode="tags" placeholder="输入标签后回车" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}

export default CaseGenerationPage
