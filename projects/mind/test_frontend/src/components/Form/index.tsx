import React, { useContext, useEffect } from 'react'
import type { FormInstance, FormRule, GetProp } from 'antd'
import {
  AutoComplete,
  Button,
  Checkbox,
  Divider,
  Flex,
  Form,
  Input,
  InputNumber,
  Radio,
  Select,
  Space,
  Switch,
  TreeSelect,
} from 'antd'
import IconPicker from './icon-picker'
import style from './style.module.less'
import JsonInput from './json-input'
import DatePicker from './date-picker'
import DatetimePicker from './datetime-picker'
import TimePicker from './time-picker'
import { MessageContext } from '@/context/messageContext'
import { filterOption } from '@/utils'
import DomainInput from './domain-input'
import ArrayInput from './array-input'
import ArrayItem, { type Item } from './array-item'
import ObjectItem from './object-item'
import EditorInput from './editor-input'
import ArrayArrayItem from './array-array-item'

type Options = GetProp<typeof Select, 'options'>

type TreeData = GetProp<typeof TreeSelect, 'treeData'>

type FormDataType = (AnyObject & { id?: string }) | AnyObject

const formItemGap = 16

export interface FormItem {
  label?: React.ReactNode
  name?: string | string[]
  type?: string
  placeholder?: string
  hidden?: boolean
  required?: boolean
  disabled?: boolean
  style?: React.CSSProperties
  rules?: FormRule[]
  options?: Options
  treeData?: TreeData
  children?: React.ReactNode
  itemList?: Item[]
  col?: 1 | 2 | 3 | 4
  props?: any
}

export type FormProps<T> = {
  formList: FormItem[]
  formData: T
  form?: FormInstance
  labelWidth?: number
  loading?: boolean
  showAction?: boolean
  cancelText?: string
  submitText?: string
  actionButton?: React.ReactNode
  disabled?: boolean
  setFormData: (data: T) => void
  setForm?: (form: FormInstance) => void
  createApi?: (data: T) => Promise<unknown>
  updateApi?: (data: T) => Promise<unknown>
  onFinish?: (values: T) => void
  onSuccess?: (values?: T) => void
  onCancel?: () => void
  onValuesChange?: (changedValues: T, allValues: T) => void
  cols?: number
  validateTrigger?: string | string[]
}

const getRules = (item: FormItem) => {
  const rules = [...(item.rules || [])]

  if (item.required) {
    const labelText = typeof item.label === 'string' ? item.label : '该字段'
    rules.push({ required: true, message: `请先填写${labelText}后提交！` })
  }

  return rules
}

const ExForm = <T extends FormDataType = FormDataType>(props: FormProps<T>) => {
  let [form] = Form.useForm()
  const messageApi = useContext(MessageContext)
  if (props.form) form = props.form

  const {
    formList,
    formData,
    cancelText = '取消',
    submitText = '保存',
    labelWidth = 80,
    loading,
    showAction = true,
    disabled = false,
    setForm,
    setFormData,
    onCancel,
    onValuesChange,
    actionButton,
    validateTrigger,
  } = props

  // 计算每个formItem宽度
  const getColWidth = (col?: number) => {
    const cols = props.cols || 1
    if (!col || col < 0) col = 1
    if (col > cols) col = cols
    return `calc(${(100 / cols) * col}% - ${Math.ceil((col * formItemGap * (cols - 1)) / cols) - formItemGap * (col - 1)}px)`
  }

  const getItemText = (item: FormItem) => {
    if (item.options?.length) {
      return item.options?.find((option) => {
        return option.value === getValueByKey(formData, item.name)
      })?.label as string
    }

    return getValueByKey(formData, item.name) as string
  }

  const getValueByKey = (obj?: Record<string, unknown>, key?: string | string[]) => {
    if (!obj) return undefined

    if (typeof key === 'string') return obj[key]

    if (Array.isArray(key)) {
      return key.reduce((prev, cur) => {
        return prev[cur] as Record<string, unknown>
      }, obj)
    }

    return obj
  }

  useEffect(() => {
    form.resetFields()
    form.setFieldsValue(formData || {})
  }, [formData, form])

  useEffect(() => {
    setForm?.(form)
  }, [setForm, form])

  const onFinish = (values: T) => {
    const _values = { ...props.formData, ...values }

    setFormData(_values)

    props.onFinish?.(_values)

    const API = _values._id || _values.id ? props.updateApi : props.createApi
    API?.(_values).then((res) => {
      if (res) {
        messageApi.success('保存成功')
        props.onSuccess?.(_values)
      }
    })
  }

  return (
    <Form
      form={form}
      className={style.exForm}
      disabled={disabled}
      labelCol={{
        style: { minWidth: labelWidth },
      }}
      labelWrap
      initialValues={formData}
      onFinish={onFinish}
      autoComplete="off"
      validateTrigger={validateTrigger}
      onValuesChange={onValuesChange}
    >
      <Flex gap={`0 ${formItemGap}px`} wrap="wrap">
        {formList
          .filter((item) => !item.hidden)
          .map((item, index) => {
            const fieldDisabled = disabled || item.disabled

            if (item.type === 'title')
              return (
                <Divider key={item.name?.toString() || index} orientation="left" style={{ marginTop: 0 }}>
                  {!!item.label && <b>{item.label}</b>}
                  {!!item.children && item.children}
                </Divider>
              )

            if (item.type === 'custom') return <span key={item.name?.toString() || index}>{item.children}</span>

            return (
              <Form.Item
                key={item.name?.toString() || index}
                label={item.label}
                name={item.name}
                rules={getRules(item)}
                valuePropName={['checkbox', 'switch'].includes(item.type || '') ? 'checked' : 'value'}
                style={{ width: getColWidth(item.col), ...item.style }}
              >
                {item.type === 'text' && <span>{getItemText(item)}</span>}
                {item.type === 'input' && (
                  <Input
                    placeholder={item.placeholder || `请输入${item.label}`}
                    disabled={fieldDisabled}
                    {...item.props}
                  />
                )}
                {item.type === 'arrayInput' && (
                  <ArrayInput placeholder={`请输入${item.label}`} disabled={fieldDisabled} {...item.props} />
                )}
                {item.type === 'arrayItem' && (
                  <ArrayItem disabled={fieldDisabled} itemList={item.itemList || []} {...item.props} />
                )}
                {item.type === 'arrayArrayItem' && (
                  <ArrayArrayItem disabled={fieldDisabled} itemList={item.itemList || []} {...item.props} />
                )}
                {item.type === 'objectItem' && (
                  <ObjectItem disabled={fieldDisabled} itemList={item.itemList || []} {...item.props} />
                )}
                {item.type === 'password' && (
                  <Input.Password
                    placeholder={item.placeholder || `请输入${item.label}`}
                    disabled={item.disabled}
                    {...item.props}
                  />
                )}
                {item.type === 'number' && (
                  <InputNumber
                    style={{ width: '100%' }}
                    placeholder={item.placeholder || `请输入${item.label}`}
                    disabled={item.disabled}
                    {...item.props}
                  />
                )}
                {item.type === 'autoComplete' && (
                  <AutoComplete
                    style={{ width: '100%' }}
                    placeholder={item.placeholder || `请输入${item.label}`}
                    options={item.options}
                    filterOption={filterOption}
                    allowClear={true}
                    disabled={item.disabled}
                    {...item.props}
                  />
                )}
                {item.type === 'switch' && <Switch disabled={item.disabled} {...item.props} />}
                {item.type === 'radio' && (
                  <Radio.Group disabled={item.disabled} options={item.options} {...item.props} />
                )}
                {item.type === 'checkbox' && <Checkbox disabled={item.disabled} {...item.props} />}
                {item.type === 'checkboxGroup' && (
                  <Checkbox.Group disabled={item.disabled} options={item.options} {...item.props} />
                )}
                {item.type === 'select' && (
                  <Select
                    options={item.options || []}
                    placeholder={item.placeholder || `请选择${item.label}`}
                    showSearch
                    allowClear
                    filterOption={filterOption}
                    disabled={item.disabled}
                    {...item.props}
                  />
                )}

                {item.type === 'treeSelect' && (
                  <TreeSelect
                    showSearch
                    placeholder={item.placeholder || `请选择${item.label}`}
                    allowClear
                    treeLine
                    treeIcon
                    treeDefaultExpandAll
                    treeData={item.treeData || []}
                    treeNodeFilterProp="title"
                    disabled={item.disabled}
                    {...item.props}
                  />
                )}
                {item.type === 'date' && (
                  <DatePicker
                    placeholder={item.placeholder || `请选择${item.label}`}
                    disabled={item.disabled}
                    {...item.props}
                  />
                )}
                {item.type === 'datetime' && (
                  <DatetimePicker
                    placeholder={item.placeholder || `请选择${item.label}`}
                    disabled={item.disabled}
                    {...item.props}
                  />
                )}
                {item.type === 'time' && (
                  <TimePicker
                    placeholder={item.placeholder || `请选择${item.label}`}
                    disabled={item.disabled}
                    {...item.props}
                  />
                )}
                {item.type === 'textarea' && (
                  <Input.TextArea
                    rows={4}
                    placeholder={item.placeholder || `请输入${item.label}`}
                    disabled={item.disabled}
                    {...item.props}
                  />
                )}
                {item.type === 'icon' && <IconPicker />}
                {item.type === 'json' && <JsonInput options={item.options} disabled={item.disabled} {...item.props} />}
                {item.type === 'editor' && <EditorInput disabled={item.disabled} {...item.props} />}
                {item.type === 'domain' && <DomainInput disabled={item.disabled} {...item.props} />}
                {item.children}
              </Form.Item>
            )
          })}
      </Flex>

      {showAction && (
        <Form.Item style={{ textAlign: 'right' }}>
          <Space size="middle">
            <Button onClick={onCancel} disabled={loading}>
              {cancelText}
            </Button>
            <Button type="primary" loading={loading} htmlType="submit">
              {submitText}
            </Button>
            {actionButton}
          </Space>
        </Form.Item>
      )}
    </Form>
  )
}

export default ExForm
