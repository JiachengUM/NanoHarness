import { useEffect, useState } from 'react'
import Api from '@/apis/task-data'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons'
import { Button, Form, Input, InputNumber, Space } from 'antd'

interface EvaluationForm extends Evaluation, Common {}

const defaultForm: EvaluationForm = {}

type Props = {
  data?: TaskRunItem
  onSuccess?: () => void
  onCancel?: () => void
}

const App = (props: Props) => {
  const [evalData, setEvalData] = useState<TaskRunItemEval>()
  const [formData, setFormData] = useState<EvaluationForm>(defaultForm)

  const formList: FormItem[] = [
    {
      label: '回复评分',
      name: 'score',
      type: 'number',
      placeholder: '请输入0-5的评分',
    },
    {
      label: '评分原因',
      name: 'comment',
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
                    <Form.Item {...restField} noStyle name={[name, 'name']}>
                      <Input style={{ width: 120 }} placeholder="评价指标" />
                    </Form.Item>

                    <Form.Item {...restField} noStyle name={[name, 'value']}>
                      <InputNumber style={{ width: 100 }} placeholder="指标打分" />
                    </Form.Item>
                    <Form.Item {...restField} noStyle name={[name, 'comment']}>
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

  const onFinish = (data: EvaluationForm) => {
    const updateData = { ...evalData, human_evaluation: data }
    Api.taskRunItem.eval.update(updateData).then(() => {
      props.onSuccess?.()
    })
  }

  const loadEval = (id?: string) => {
    if (id) {
      Api.taskRunItem.eval.get_by_item_id(id).then((res) => {
        setEvalData(res)
        setFormData((res?.human_evaluation as EvaluationForm) || defaultForm)
      })
    }
  }

  useEffect(() => {
    loadEval(props.data?.id)
  }, [props.data?.id])

  const formpProps: FormProps<EvaluationForm> = {
    formList,
    formData,
    setFormData,
    onFinish,
    onCancel: props.onCancel,
  }

  return (
    <>
      <ExForm<EvaluationForm> {...formpProps} />
    </>
  )
}

export default App
