import { useEffect, useMemo, useState } from 'react'
import { Button, Form, Input, Modal, Select, Space, Table, Tag, message } from 'antd'
import type { TableColumnsType } from 'antd'
import { useLocation, useParams } from 'react-router'
import Api from '@/apis/data-generation'
import ExDeleteButton from '@/components/DeleteButton'

type ScenarioFormValues = Pick<GenerationScenario, 'scenario_id' | 'scenario_name' | 'description' | 'tags'> & {
  tag_tree_id?: string
}

const ScenarioPage: React.FC = () => {
  const { taskId } = useParams()
  const location = useLocation()
  const taskName = (location.state as { taskName?: string } | null)?.taskName

  const [scenarios, setScenarios] = useState<GenerationScenario[]>([])
  const [tagTrees, setTagTrees] = useState<TagTreeBrief[]>([])
  const [loading, setLoading] = useState(false)
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<GenerationScenario>()
  const [scenarioForm] = Form.useForm<ScenarioFormValues>()
  const [pagination, setPagination] = useState({ current: 1, pageSize: 10 })

  const loadScenarios = async () => {
    if (!taskId) return
    setLoading(true)
    try {
      setScenarios(await Api.scenario.list({ generation_task_id: taskId }))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    Api.tagTree.list().then(setTagTrees)
    loadScenarios()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId])

  const tagTreeOptions = useMemo(
    () => tagTrees.map((tree) => ({ label: tree.name, value: tree.id })),
    [tagTrees]
  )

  const closeForm = () => {
    setFormOpen(false)
    setEditing(undefined)
    scenarioForm.resetFields()
  }

  const openCreate = () => {
    setEditing(undefined)
    scenarioForm.resetFields()
    setFormOpen(true)
  }

  const openEdit = (record: GenerationScenario) => {
    setEditing(record)
    scenarioForm.setFieldsValue({
      scenario_id: record.scenario_id,
      scenario_name: record.scenario_name,
      description: record.description,
      tags: record.tags || [],
    })
    setFormOpen(true)
  }

  const saveScenario = async () => {
    if (!taskId) return
    const values = await scenarioForm.validateFields()
    const { tag_tree_id, ...scenarioValues } = values

    if (editing?.id) {
      await Api.scenario.update({ ...editing, ...scenarioValues })
      message.success('场景已更新')
    } else {
      await Api.scenario.create({
        ...scenarioValues,
        generation_task_id: taskId,
        tag_tree_id,
      } as GenerationScenario)
      message.success('场景已新增')
    }

    closeForm()
    loadScenarios()
  }

  const columns: TableColumnsType<GenerationScenario> = [
    { title: '场景 ID', dataIndex: 'scenario_id', width: 180 },
    { title: '场景名称', dataIndex: 'scenario_name', width: 180 },
    { title: '描述', dataIndex: 'description', ellipsis: true },
    {
      title: '标签',
      dataIndex: 'tags',
      width: 260,
      render: (tags: string[]) => tags?.map((tag) => <Tag key={tag}>{tag}</Tag>),
    },
    {
      title: '操作',
      width: 120,
      render: (_, record) => (
        <Space>
          <a onClick={() => openEdit(record)}>编辑</a>
          <ExDeleteButton
            id={record.id}
            API={Api.scenario.del}
            onSuccess={loadScenarios}
          />
        </Space>
      ),
    },
  ]

  return (
    <>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          合成任务：{taskName || taskId}
        </div>
        <Button type="primary" onClick={openCreate}>新增场景</Button>
      </div>

      <Table
        rowKey={(record) => record.id || record.scenario_id}
        loading={loading}
        columns={columns}
        dataSource={scenarios}
        pagination={{
          ...pagination,
          total: scenarios.length,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (total) => `共 ${total} 条`,
          pageSizeOptions: ['10', '20', '50', '100'],
          onChange: (page, pageSize) => {
            setPagination({ current: page, pageSize })
          },
        }}
      />

      <Modal
        title={editing ? '编辑场景' : '新增场景'}
        open={formOpen}
        onCancel={closeForm}
        onOk={saveScenario}
        width={720}
        destroyOnHidden
      >
        <Form form={scenarioForm} layout="vertical">
          <Form.Item label="场景 ID" name="scenario_id" rules={[{ required: true, message: '请输入场景 ID' }]}>
            <Input placeholder="例如：scenario_001" disabled={!!editing} />
          </Form.Item>
          <Form.Item label="场景名称" name="scenario_name" rules={[{ required: true, message: '请输入场景名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item label="描述" name="description" rules={[{ required: true, message: '请输入场景描述' }]}>
            <Input.TextArea rows={5} />
          </Form.Item>
          <Form.Item label="标签" name="tags" rules={[{ required: true, type: 'array', min: 1, message: '请至少输入一个标签' }]}>
            <Select mode="tags" placeholder="输入标签后回车" />
          </Form.Item>
          {!editing && tagTreeOptions.length > 0 && (
            <Form.Item label="关联测试维度（可选）" name="tag_tree_id">
              <Select allowClear options={tagTreeOptions} placeholder="选择测试维度" />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </>
  )
}

export default ScenarioPage
