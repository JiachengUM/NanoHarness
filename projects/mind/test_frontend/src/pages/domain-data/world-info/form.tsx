import { useEffect, useMemo, useState } from 'react'
import Api from '@/apis/domain-data'
import type { FormItem, FormProps } from '@/components/Form'
import ExForm from '@/components/Form'
import { Radio } from 'antd'
import { DOMAIN_FORM_TYPE_OPTIONS } from '@/constants'

const defaultForm: WorldInfo = {}

type Props = {
  formData?: WorldInfo
  onSuccess?: () => void
  onCancel?: () => void
}

const App = (props: Props) => {
  const [formData, setFormData] = useState<WorldInfo>(defaultForm)
  const [editType, setEditType] = useState<string>('json')

  const formList: FormItem[] = useMemo(() => {
    const list: FormItem[] = [
      {
        label: '摘要信息',
        name: 'brief',
        type: 'input',
        required: true,
      },
      {
        label: '',
        name: 'entity-title',
        type: 'title',
        children: (
          <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
            <b>实体信息</b>
            <Radio.Group
              value={editType}
              options={DOMAIN_FORM_TYPE_OPTIONS}
              size="small"
              optionType="button"
              buttonStyle="solid"
              onChange={(e) => setEditType(e.target.value)}
            />
          </div>
        ),
      },
    ]

    const jsonFormList: FormItem[] = [
      {
        label: '实体信息',
        name: 'entity',
        type: 'json',
      },
    ]

    const entityFormList: FormItem[] = [
      {
        label: '城市信息',
        name: ['entity', 'city'],
        type: 'title',
      },
      {
        label: '城市名称',
        name: ['entity', 'city', 'name'],
        type: 'input',
      },
      {
        label: '城市ID',
        name: ['entity', 'city', 'id'],
        type: 'input',
      },
      {
        label: '纬度',
        name: ['entity', 'city', 'lat'],
        type: 'input',
      },
      {
        label: '经度',
        name: ['entity', 'city', 'lon'],
        type: 'input',
      },
      {
        label: '二级行政区',
        name: ['entity', 'city', 'adm2'],
        type: 'input',
      },
      {
        label: '一级行政区',
        name: ['entity', 'city', 'adm1'],
        type: 'input',
      },
      {
        label: '国家',
        name: ['entity', 'city', 'country'],
        type: 'input',
      },
      {
        label: '时区',
        name: ['entity', 'city', 'tz'],
        type: 'input',
      },
      {
        label: '类型',
        name: ['entity', 'city', 'type'],
        type: 'input',
      },
      {
        label: '天气信息',
        name: ['entity', 'weather'],
        type: 'title',
      },
      {
        label: '观测时间',
        name: ['entity', 'weather', 'obs_time'],
        type: 'input',
      },
      {
        label: '温度',
        name: ['entity', 'weather', 'temp'],
        type: 'input',
      },
      {
        label: '体感温度',
        name: ['entity', 'weather', 'feels_like'],
        type: 'input',
      },
      {
        label: '天气现象',
        name: ['entity', 'weather', 'text'],
        type: 'input',
      },
      {
        label: '风向',
        name: ['entity', 'weather', 'wind_dir'],
        type: 'input',
      },
      {
        label: '风力等级',
        name: ['entity', 'weather', 'wind_scale'],
        type: 'input',
      },
      {
        label: '风速',
        name: ['entity', 'weather', 'wind_speed'],
        type: 'input',
      },
      {
        label: '相对湿度',
        name: ['entity', 'weather', 'humidity'],
        type: 'input',
      },
      {
        label: '降水量',
        name: ['entity', 'weather', 'precip'],
        type: 'input',
      },
      {
        label: '云量',
        name: ['entity', 'weather', 'cloud'],
        type: 'input',
      },
      {
        label: '大气压强',
        name: ['entity', 'weather', 'pressure'],
        type: 'input',
      },
      {
        label: '能见度',
        name: ['entity', 'weather', 'vis'],
        type: 'input',
      },
      {
        label: '日期信息',
        name: ['entity', 'date'],
        type: 'title',
      },
      {
        label: '日期',
        name: ['entity', 'date', 'date'],
        type: 'input',
      },
      {
        label: '农历日期',
        name: ['entity', 'date', 'lunar_date'],
        type: 'input',
      },
      {
        label: '农历节日',
        name: ['entity', 'date', 'lunar_holiday'],
        type: 'input',
      },
      {
        label: '公历节日',
        name: ['entity', 'date', 'solar_holiday'],
        type: 'input',
      },
      {
        label: '节气',
        name: ['entity', 'date', 'solar_terms'],
        type: 'input',
      },
      {
        label: '其他信息',
        name: ['entity', 'attributes-title'],
        type: 'title',
      },
      {
        label: '其他属性',
        name: ['entity', 'attributes'],
        type: 'json',
      },
    ]

    if (editType === 'json') list.push(...jsonFormList)
    if (editType === 'form') list.push(...entityFormList)

    return list
  }, [editType])

  useEffect(() => {
    setFormData(props.formData || defaultForm)
  }, [props.formData])

  const formpProps: FormProps<WorldInfo> = {
    formList,
    formData,
    setFormData,
    labelWidth: 100,
    createApi: Api.worldInfo.create,
    updateApi: Api.worldInfo.update,
    onCancel: props.onCancel,
    onSuccess: props.onSuccess,
  }

  return (
    <>
      <ExForm<WorldInfo> {...formpProps} />
    </>
  )
}

export default App
