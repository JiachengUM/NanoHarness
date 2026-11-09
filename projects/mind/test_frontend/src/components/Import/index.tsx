import { useContext, useState } from 'react'
import type { GetProp, UploadFile, UploadProps } from 'antd'
import { Button, Form, Space, Upload } from 'antd'
import { UploadOutlined } from '@ant-design/icons'
import { MessageContext } from '@/context/messageContext'
import { AGENT_ARENA_BASE_URL } from '@/request/https'
import useApiModeStore from '@/stores/apiMode'

type FileType = Parameters<GetProp<UploadProps, 'beforeUpload'>>[0]

type FormValues = {
  name: string
}

type Props = {
  action: string
  accept?: string
  templates?: { url?: string; name?: string }[]
  params?: Record<string, unknown>
  onCancel?: () => void
  onSuccess?: () => void
}

const Import: React.FC<Props> = (props) => {
  const [form] = Form.useForm<FormValues>()
  const messageApi = useContext(MessageContext)
  const [files, setFiles] = useState<UploadFile[]>([])
  const [loading, setLoading] = useState(false)

  const fileAccept = props.accept || '.json,.jsonl,.xls,.xlsx'

  const handleBeforeUpload = (file: UploadFile) => {
    setFiles((prev) => {
      if (prev.find((f) => f.name === file.name && f.size === file.size)) return prev

      return [...prev, file]
    })
    const values = form.getFieldsValue()
    if (!values.name) {
      form.setFieldValue('name', file.name)
    }
    return false
  }

  const handleRemove = (file: UploadFile) => {
    const index = files.indexOf(file)
    const newFileList = files.slice()
    newFileList.splice(index, 1)
    setFiles(newFileList)
  }

  // 开始导入
  const onFinish = (values: { name: string }) => {
    if (!files.length) return messageApi.error('请选择文件！')

    const formData = new FormData()
    files.forEach((file) => {
      formData.append('file', file as FileType)
    })
    formData.append('name', values.name)
    if (props.params) {
      Object.entries(props.params).forEach(([key, value]) => {
        formData.append(key, String(value))
      })
    }
    setLoading(true)

    messageApi.loading({ content: '数据导入中，请稍后...', key: 'import-loading', duration: 0 })

    let action = props.action.startsWith(AGENT_ARENA_BASE_URL) ? props.action : `${AGENT_ARENA_BASE_URL}${props.action}`

    const resolveFullUrl = useApiModeStore.getState().resolveFullUrl
    action = resolveFullUrl(action, AGENT_ARENA_BASE_URL)

    fetch(action, {
      method: 'POST',
      body: formData,
    })
      .then((res) => res.json())
      .then((res) => {
        if (res.code === 200) {
          messageApi.success(res.message || '数据导入成功!')
          props.onSuccess?.()
        } else {
          messageApi.error(`数据导入失败: ${res.message || '未知错误'}`)
        }
      })
      .catch(() => {
        messageApi.error('网络请求失败，请检查网络后重试')
      })
      .finally(() => {
        setLoading(false)
        messageApi.destroy('import-loading')
      })
  }

  return (
    <Form<FormValues>
      form={form}
      autoComplete="off"
      labelWrap
      labelCol={{
        style: { minWidth: 80 },
      }}
      onFinish={onFinish}
    >
      <Form.Item name="name" label="文件模板">
        {props.templates?.map((item) => (
          <div style={{ lineHeight: '32px', display: 'flex', gap: 12 }}>
            <div style={{ minWidth: 80 }}>{item.name || '导入模板'}</div>
            <a href={item.url || ''} download={item.name || '导入模板.json'}>
              点击下载
            </a>
          </div>
        ))}
      </Form.Item>

      <Form.Item label="导入文件">
        <Upload
          beforeUpload={handleBeforeUpload}
          onRemove={handleRemove}
          fileList={files}
          maxCount={10}
          multiple={false}
          accept={fileAccept}
        >
          <Button type="primary" icon={<UploadOutlined />}>
            选择{fileAccept}文件
          </Button>
        </Upload>
      </Form.Item>

      <Form.Item style={{ textAlign: 'right' }}>
        <Space size="middle">
          <Button disabled={loading} onClick={props.onCancel}>
            取消
          </Button>
          <Button type="primary" htmlType="submit" loading={loading}>
            导入
          </Button>
        </Space>
      </Form.Item>
    </Form>
  )
}

export default Import
