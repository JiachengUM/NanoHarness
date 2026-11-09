import { useEffect, useState } from 'react'
import { Alert, Button, Form, Input, Modal, Popconfirm, Space, Table, Tag, Tree, Upload, message } from 'antd'
import type { DataNode } from 'antd/es/tree'
import type { TableColumnsType, UploadFile } from 'antd'
import type { RcFile } from 'antd/es/upload/interface'
import { UploadOutlined } from '@ant-design/icons'
import Api from '@/apis/data-generation'

type UploadForm = {
  name: string
  description?: string
  treeJson?: string
}

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

const TagTreePage: React.FC = () => {
  const [data, setData] = useState<TagTreeBrief[]>([])
  const [loading, setLoading] = useState(false)
  const [formOpen, setFormOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewTreeData, setPreviewTreeData] = useState<DataNode[]>([])
  const [previewTreeName, setPreviewTreeName] = useState('')
  const [previewTotalLeaves, setPreviewTotalLeaves] = useState(0)
  const [file, setFile] = useState<RcFile>()
  const [editingTree, setEditingTree] = useState<TagTreeDetail>()
  const [form] = Form.useForm<UploadForm>()

  const load = async () => {
    setLoading(true)
    try {
      setData(await Api.tagTree.list())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const showPreview = async (record: TagTreeBrief) => {
    if (!record.id) return
    setPreviewTreeName(record.name)
    setPreviewLoading(true)
    setPreviewOpen(true)
    try {
      const detail = await Api.tagTree.detail(record.id)
      const treeData = detail.tree as { root?: TagTreeNodeRaw }
      if (treeData?.root) {
        const result = countAndConvertNode(treeData.root, '0')
        setPreviewTreeData([result.node])
        setPreviewTotalLeaves(result.leafCount)
      } else {
        setPreviewTreeData([])
        setPreviewTotalLeaves(0)
      }
    } catch (error) {
      message.error('加载测试维度失败')
    } finally {
      setPreviewLoading(false)
    }
  }

  const closeForm = () => {
    setFormOpen(false)
    setEditingTree(undefined)
    setFile(undefined)
    form.resetFields()
  }

  const openCreate = () => {
    setEditingTree(undefined)
    setFile(undefined)
    form.setFieldsValue({
      name: '',
      description: '',
      treeJson: '',
    })
    setFormOpen(true)
  }

  const openEdit = async (record: TagTreeBrief) => {
    if (!record.id) return
    const detail = await Api.tagTree.detail(record.id)
    setEditingTree(detail)
    setFile(undefined)
    form.setFieldsValue({
      name: detail.name,
      description: detail.description,
      treeJson: JSON.stringify(detail.tree, null, 2),
    })
    setFormOpen(true)
  }

  const deleteTree = async (record: TagTreeBrief) => {
    if (!record.id) return
    await Api.tagTree.del(record.id)
    message.success('删除成功')
    load()
  }

  const exportTree = async (record: TagTreeBrief) => {
    if (!record.id) return
    const response = await fetch(Api.tagTree.exportUrl(record.id))
    if (!response.ok) {
      message.error('导出失败')
      return
    }

    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${record.name}.json`
    link.click()
    window.URL.revokeObjectURL(url)
  }

  const submitForm = async () => {
    const values = await form.validateFields()
    const treeText = values.treeJson?.trim()
    if (!treeText && !file && !editingTree?.tree) {
      message.error('请上传 JSON 文件或直接编辑 JSON 内容')
      return
    }

    setSubmitting(true)
    try {
      const tree = treeText
        ? JSON.parse(treeText)
        : file
          ? JSON.parse(await file.text())
          : editingTree?.tree
      if (!tree) {
        message.error('标签树 JSON 不能为空')
        return
      }

      if (editingTree?.id) {
        await Api.tagTree.update(editingTree.id, { name: values.name, description: values.description, tree })
        message.success('更新成功')
      } else {
        await Api.tagTree.create({ name: values.name, description: values.description, tree })
        message.success('新增成功')
      }

      closeForm()
      load()
    } catch (error) {
      if (error instanceof SyntaxError) message.error('JSON 文件格式不正确')
    } finally {
      setSubmitting(false)
    }
  }

  const columns: TableColumnsType<TagTreeBrief> = [
    { title: '名称', dataIndex: 'name' },
    { title: '描述', dataIndex: 'description' },
    {
      title: '操作',
      width: 220,
      render: (_, record) => (
        <Space>
          <a onClick={() => showPreview(record)}>预览</a>
          <a onClick={() => exportTree(record)}>导出</a>
          <a onClick={() => openEdit(record)}>编辑</a>
          <Popconfirm
            title="删除测试维度"
            description={`确认删除「${record.name}」？`}
            onConfirm={() => deleteTree(record)}
          >
            <a>删除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <>
      <div style={{ marginBottom: 16, textAlign: 'right' }}>
        <Button type="primary" onClick={openCreate}>新增测试维度</Button>
      </div>
      <Table rowKey={(record) => record.id || record.name} loading={loading} columns={columns} dataSource={data} />

      <Modal
        title={editingTree ? '编辑测试维度' : '新增测试维度'}
        open={formOpen}
        confirmLoading={submitting}
        onCancel={closeForm}
        onOk={submitForm}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item label="名称" name="name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item label="描述" name="description">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item
            label="标签树 JSON"
            extra="支持直接编辑标签树 JSON，也可上传文件覆盖。两者同时提供时以文本框内容为准。"
          >
            <Form.Item
              name="treeJson"
              noStyle
              rules={[
                {
                  validator: async (_, value) => {
                    const treeText = typeof value === 'string' ? value.trim() : ''
                    if (!treeText && !file && !editingTree?.tree) {
                      return Promise.reject(new Error('请上传 JSON 文件或输入 JSON 内容'))
                    }
                    if (treeText) {
                      try {
                        JSON.parse(treeText)
                      } catch {
                        return Promise.reject(new Error('JSON 格式不正确'))
                      }
                    }
                    return Promise.resolve()
                  },
                },
              ]}
            >
              <Input.TextArea rows={10} placeholder='例如：{"name":"根节点","children":[]}' />
            </Form.Item>
          </Form.Item>
          <Form.Item
            label="上传 JSON 文件（可选）"
            extra={editingTree ? '编辑时可不上传文件，直接修改上方 JSON。' : '新增时可选择上传文件快速填充 JSON。'}
          >
            <Upload
              accept=".json"
              maxCount={1}
              fileList={
                file
                  ? [{
                      uid: file.uid,
                      name: file.name,
                      status: 'done',
                      originFileObj: file,
                    } satisfies UploadFile]
                  : []
              }
              beforeUpload={(nextFile) => {
                setFile(nextFile)
                return false
              }}
              onRemove={() => setFile(undefined)}
            >
              <Button icon={<UploadOutlined />}>选择文件</Button>
            </Upload>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`测试维度预览：${previewTreeName}`}
        width={700}
        open={previewOpen}
        onCancel={() => setPreviewOpen(false)}
        footer={<Button onClick={() => setPreviewOpen(false)}>关闭</Button>}
        destroyOnHidden
      >
        {previewLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>加载中...</div>
        ) : previewTreeData.length > 0 ? (
          <>
            <Alert
              style={{ marginBottom: 12 }}
              type="info"
              showIcon
              message={`共 ${previewTotalLeaves} 个叶子标签`}
            />
            <div style={{ maxHeight: 500, overflow: 'auto', padding: '8px 0', border: '1px solid #f0f0f0', borderRadius: 4 }}>
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
    </>
  )
}

export default TagTreePage
