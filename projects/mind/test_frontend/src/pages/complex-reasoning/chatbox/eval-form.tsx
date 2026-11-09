import { useEffect, useState } from 'react'
import Api from '@/apis/task-data'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons'
import { Button, Form, Input, InputNumber, Space } from 'antd'

const defaultForm: EvaluationResult = {}

type Props = {
  data?: EvaluationForm
  onSuccess?: () => void
  onCancel?: () => void
}

const App = (props: Props) => {
  const [formData, setFormData] = useState<EvaluationResult>(defaultForm)

  const formList: FormItem[] = [
    {
      label: '回复评分',
      name: 'overall_score',
      type: 'number',
      placeholder: '请输入0-5的评分',
    },
    {
      label: '评分原因',
      name: 'overall_reason',
      type: 'textarea',
    },
    {
      label: '指标评价',
      name: 'metrics',
      children: (
        <Form.List name="metrics">
          {(fields, { add, remove }) => (
            <>
              {fields.map(({ key, name, ...restField }) => {
                return (
                  <Space.Compact style={{ width: '100%', marginBottom: 8 }} key={key}>
                    <Form.Item {...restField} noStyle name={[name, 'metric_name']}>
                      <Input style={{ width: 120 }} placeholder="评价指标" />
                    </Form.Item>

                    <Form.Item {...restField} noStyle name={[name, 'score']}>
                      <InputNumber style={{ width: 100 }} placeholder="指标打分" />
                    </Form.Item>
                    <Form.Item {...restField} noStyle name={[name, 'reason']}>
                      <Input style={{ flex: 1 }} placeholder="打分原因" />
                    </Form.Item>
                    <Button danger type="text" onClick={() => remove(name)} icon={<MinusCircleOutlined />} />
                  </Space.Compact>
                )
              })}
              <Form.Item style={{ marginBottom: 0 }}>
                <Button type="primary" onClick={() => add()} block icon={<PlusOutlined />}>
                  添加评价指标
                </Button>
              </Form.Item>
            </>
          )}
        </Form.List>
      ),
    },
  ]

  const onFinish = (data: EvaluationResult) => {
    if (data.metrics?.length) {
      localStorage.setItem('metrics', JSON.stringify(data.metrics.map((item) => ({ metric_name: item.metric_name }))))
    }

    Api.chatHistory.eval({ ...props.data, human_evaluation: data }).then(() => {
      props.onSuccess?.()
    })
  }

  useEffect(() => {
    setFormData(props.data?.human_evaluation || defaultForm)
  }, [props.data])

  const formpProps: FormProps<EvaluationResult> = {
    formList,
    formData,
    setFormData,
    onFinish,
    onCancel: props.onCancel,
  }

  return (
    <>
      <ExForm<EvaluationResult> {...formpProps} />
    </>
  )
}

export default App
