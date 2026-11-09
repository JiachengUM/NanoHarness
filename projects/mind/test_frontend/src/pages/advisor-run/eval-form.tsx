import { useEffect, useState } from 'react'
import Api from '@/apis/task-data'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons'
import { Button, Form, Input, InputNumber, Space } from 'antd'

const defaultForm: AdvisorRun = {}

type Props = {
  record?: AdvisorRun
  onSuccess?: (data?: AdvisorRun) => void
  onCancel?: () => void
}

const App = (props: Props) => {
  const [formData, setFormData] = useState<AdvisorRun>(props.record || defaultForm)

  const formList: FormItem[] = [
    {
      label: '评价得分',
      name: ['manual_evaluation', 'score'],
      type: 'number',
    },
    {
      label: '评价意见',
      name: ['manual_evaluation', 'comment'],
      type: 'textarea',
    },
    {
      label: '指标评价',
      name: ['manual_evaluation', 'metrics'],
      children: (
        <Form.List name={['manual_evaluation', 'metrics']}>
          {(fields, { add, remove }) => (
            <>
              {fields.map(({ key, name, ...restField }) => {
                return (
                  <Space.Compact style={{ width: '100%', marginBottom: 8 }} key={key}>
                    <Form.Item {...restField} noStyle name={[name, 'name']}>
                      <Input style={{ width: 120 }} placeholder="评价指标" />
                    </Form.Item>

                    <Form.Item {...restField} noStyle name={[name, 'value']}>
                      <InputNumber style={{ width: 100 }} placeholder="指标得分" />
                    </Form.Item>
                    <Form.Item {...restField} noStyle name={[name, 'comment']}>
                      <Input style={{ flex: 1 }} placeholder="评价意见" />
                    </Form.Item>
                    <Button danger type="text" onClick={() => remove(name)} icon={<MinusCircleOutlined />} />
                  </Space.Compact>
                )
              })}
              <Form.Item style={{ marginBottom: 0 }}>
                <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>
                  添加评价指标
                </Button>
              </Form.Item>
            </>
          )}
        </Form.List>
      ),
    },
  ]

  const onFinish = (data: AdvisorRun) => {
    if (data.manual_evaluation?.metrics?.length) {
      localStorage.setItem(
        'eval_metrics',
        JSON.stringify(data.manual_evaluation.metrics.map((item) => ({ name: item.name })))
      )
    }

    Api.advisorRun.update(data).then(() => {
      props.onSuccess?.(data)
    })
  }

  useEffect(() => {
    const _formData = JSON.parse(JSON.stringify(props.record || defaultForm))

    if (!_formData.manual_evaluation) {
      _formData.manual_evaluation = {
        metrics: JSON.parse(localStorage.getItem('eval_metrics') || '[]'),
      }
    }

    setFormData(_formData)
  }, [props.record])

  const formpProps: FormProps<AdvisorRun> = {
    formList,
    formData,
    setFormData,
    onFinish,
    onCancel: props.onCancel,
  }

  return (
    <>
      <ExForm<AdvisorRun> {...formpProps} />
    </>
  )
}

export default App
