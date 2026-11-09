import { useRef, useState } from 'react'
import type { FormInstance } from 'antd'
import { AutoComplete, Button, DatePicker, Form, Input, Select, Space, TreeSelect } from 'antd'
import dayjs from 'dayjs'
import { DownOutlined, SearchOutlined, UpOutlined } from '@ant-design/icons'
import style from './search.module.less'
import { USER_NAME_LIST } from '@/constants/system'

export interface SearchItem {
  key: string // key 不能使用 nodeName，因为 nodeName 会导致 react 报错 https://github.com/facebook/react/issues/6284
  label: string
  type?: string
  defaultValue?: string | number | boolean | string[] | number[]
  placeholder?: string
  width?: number
  style?: React.CSSProperties
  showSearch?: boolean
  hidden?: boolean
  required?: boolean
  options?: OptionItem[]
  treeData?: OptionItem[]
  children?: React.ReactNode
  props?: Record<string, unknown>
}

interface SearchObject extends AnyObject {
  start_time?: string
  end_time?: string
  timeRange?: [dayjs.Dayjs, dayjs.Dayjs]
}

export interface Props<T extends SearchObject = SearchObject> {
  searchList?: SearchItem[]
  loading?: boolean
  labelWidth?: number
  initialValues?: T
  onSearch?: (form: T) => void
  onValuesChange?: (changedValues: T, allValues: T) => void
  searchHidden?: boolean
  intercept?: (res: T) => T
  form?: FormInstance<T>
  action?: React.ReactNode
}

const { RangePicker } = DatePicker

const App = <T extends SearchObject = SearchObject>(props: Props<T>) => {
  const [form] = Form.useForm<T>()
  const searchRef = useRef<HTMLDivElement>(null)
  const { loading, searchList, labelWidth = 80, onSearch, onValuesChange, searchHidden = true } = props
  const [hidden, setHidden] = useState<boolean>(true)

  const filterOption = (input: string, option?: { label: string; value: string; filterLabel?: string }) => {
    const label = option?.filterLabel || option?.label || ''
    if (typeof label !== 'string') return false
    return label.toLowerCase().includes(input.toLowerCase())
  }

  const handleSearch = () => {
    const searchForm = props.form ? props.form.getFieldsValue() : form.getFieldsValue()

    handleTimeRange(searchForm)

    let _searchForm = { ...searchForm }

    if (props.intercept) _searchForm = props.intercept(_searchForm)

    onSearch?.(_searchForm)
  }

  const handleValuesChange = (changeValue: T, allValues: T) => {
    if (changeValue?.timeRange && Array.isArray(changeValue.timeRange)) {
      changeValue.start_time = dayjs(changeValue.timeRange[0]).format('YYYY-MM-DD HH:mm:ss')
      changeValue.end_time = dayjs(changeValue.timeRange[1]).format('YYYY-MM-DD HH:mm:ss')
      if (allValues) {
        allValues.start_time = changeValue.start_time
        allValues.end_time = changeValue.end_time
      }
    }

    onValuesChange?.(changeValue, allValues)
  }

  const handleTimeRange = (searchForm: T) => {
    console.log('searchForm:', searchForm)
    if (searchList?.find((item) => item.key === 'timeRange')) {
      searchForm.start_time = ''
      searchForm.end_time = ''

      if (searchForm.timeRange && Array.isArray(searchForm.timeRange)) {
        searchForm.start_time = dayjs(searchForm.timeRange[0]).format('YYYY-MM-DD HH:mm:ss') || ''
        searchForm.end_time = dayjs(searchForm.timeRange[1]).format('YYYY-MM-DD HH:mm:ss') || ''
        delete searchForm.timeRange
      }
    }
  }

  return (
    <div className={style.search}>
      <Form
        form={props.form || form}
        autoComplete="off"
        layout="inline"
        labelCol={{
          style: { minWidth: labelWidth },
        }}
        initialValues={props.initialValues}
        onFinish={handleSearch}
        onValuesChange={handleValuesChange}
        style={{ width: '100%' }}
      >
        <div
          style={{
            flex: 1,
            height: searchHidden && hidden ? '40px' : '',
            overflow: searchHidden && hidden ? 'hidden' : '',
          }}
        >
          <div ref={searchRef} className={style.searchForm}>
            {(searchList || [])
              .filter((item) => !item.hidden)
              .map((item) => {
                return (
                  <Form.Item
                    initialValue={item.defaultValue}
                    className={style.searchItem}
                    style={item.style}
                    key={item.key}
                    label={item.label}
                    required={item.required}
                    // react bug with 'nodeName' https://github.com/facebook/react/issues/6284
                    name={!!item.type && (item.key === 'nodeName' ? '_nodeName' : item.key)}
                  >
                    {item.type === 'input' && (
                      <Input
                        allowClear
                        placeholder={item.placeholder || `请输入${item.label}`}
                        style={{ width: item.width || 180 }}
                      />
                    )}
                    {item.type === 'select' && (
                      <Select
                        allowClear
                        showSearch={typeof item.showSearch === 'boolean' ? item.showSearch : true}
                        options={item.options as { label: string; value: string }[]}
                        filterOption={filterOption}
                        placeholder={item.placeholder || `请选择${item.label}`}
                        style={{ width: item.width || 180 }}
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
                        treeData={(item.treeData as OptionItem[]) || []}
                        treeNodeFilterProp="label"
                        style={{ width: item.width || 180 }}
                        {...item.props}
                      />
                    )}
                    {item.type === 'timeRange' && (
                      <RangePicker
                        placeholder={['开始时间', '结束时间']}
                        showTime={{ format: 'HH:mm:ss' }}
                        format="YYYY-MM-DD HH:mm:ss"
                        style={{ width: item.width || 340 }}
                        {...item.props}
                      />
                    )}
                    {item.type === 'dateRange' && (
                      <RangePicker
                        placeholder={['开始时间', '结束时间']}
                        format="YYYY-MM-DD"
                        style={{ width: item.width || 240 }}
                        {...item.props}
                      />
                    )}
                    {item.type === 'user' && (
                      <AutoComplete
                        allowClear
                        placeholder={item.placeholder || `请选择${item.label}`}
                        style={{ width: item.width || 180 }}
                        options={USER_NAME_LIST.map((name) => ({ label: name, value: name }))}
                        filterOption={filterOption}
                        {...item.props}
                      />
                    )}
                    {item.children}
                  </Form.Item>
                )
              })}
          </div>
        </div>

        <Space size="middle" style={{ alignItems: 'flex-start' }}>
          <Space.Compact>
            <Form.Item style={{ margin: 0 }}>
              <Button type="primary" htmlType="submit" ghost loading={loading} icon={<SearchOutlined />}>
                搜索
              </Button>
            </Form.Item>

            {searchHidden && (searchRef.current?.clientHeight || 0) > 44 && (
              <Button
                type="primary"
                ghost
                icon={hidden ? <DownOutlined /> : <UpOutlined />}
                onClick={() => setHidden((prev) => !prev)}
              ></Button>
            )}
          </Space.Compact>
          {props.action}
        </Space>
      </Form>
    </div>
  )
}

export default App
