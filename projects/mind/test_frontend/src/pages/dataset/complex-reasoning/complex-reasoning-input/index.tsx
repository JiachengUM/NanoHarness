import { useMemo, useRef, useState } from 'react'
import { Button, Modal, Radio, Space } from 'antd'
import type { TableColumnsType } from 'antd'
import Api from '@/apis/task-data'
import ExDeleteButton from '@/components/DeleteButton'
import ExTable from '@/components/Table'
import type { HandleType } from '@/components/Table'
import Form from './form'
import ExDrawer from '@/components/Form/drawer'
import { useParams } from 'react-router'
import { removeMetaFields } from '@/utils/json'
import Import from '@/components/Import'
import { exportExcelGet, exportJsonGet } from '@/utils/export'
import { useOptions } from '@/hooks/options'
import { jsonToString } from '@/utils/json'
import BuildForm from '../dataset-build/form'

const App: React.FC = () => {
  const tableRef = useRef<HandleType<ComplexReasoningCase>>(null)
  const [open, setOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [exportFormat, setExportFormat] = useState<'json' | 'excel'>('json')
  const [formData, setFormData] = useState<ComplexReasoningCase>({})
  const [openBuild, setOpenBuild] = useState(false)
  const [buildParams, setBuildParams] = useState<DatasetBuildParams>({ dataset_item_ids: [] })
  const { dataset_id } = useParams()
  const [datasetOptions] = useOptions(Api.complexReasoningDataset.list)

  const params = useMemo(() => ({ dataset_id }), [dataset_id])

  const searchList = [
    { key: 'keyword', label: '关键词', type: 'input' },
    { key: 'creator', label: '创建人', type: 'input' },
  ]

  const renderMessageList = (messages?: Message[]) => {
    return (messages || []).map((item, idx) => (
      <div key={idx} style={{ marginBottom: 4 }}>
        <strong>{item.role}: </strong>
        <span>{item.content}</span>
      </div>
    ))
  }

  const columns: TableColumnsType<ComplexReasoningCase> = [
    {
      title: 'ID',
      dataIndex: 'id',
    },
    {
      title: 'CASE_ID',
      dataIndex: 'case_id',
    },
    {
      title: '前置对话记录',
      dataIndex: 'user_query_lists',
      render: (_, record) => (
        <div>
          {record.user_query_lists?.map((group, index) => (
            <div key={index} style={{ marginBottom: 4, padding: 4, border: '1px solid #f0f0f0' }}>
              {Array.isArray(group) ? (
                renderMessageList(group)
              ) : (
                <>
                  {renderMessageList(group.user_query_list)}
                  {!!group.mock_time && <div>mock_time: {group.mock_time}</div>}
                  {group.mock_info && <div>mock_info: {jsonToString(group.mock_info)}</div>}
                </>
              )}
            </div>
          ))}
        </div>
      ),
    },
    // {
    //   title: '剧本',
    //   dataIndex: 'expected_script',
    //   ellipsis: true,
    // },
    // {
    //   title: '自然语言断言',
    //   dataIndex: 'nl_assertion',
    //   ellipsis: true,
    // },
    // {
    //   title: '用例描述',
    //   dataIndex: 'case_description',
    //   ellipsis: true,
    // },
    // {
    //   title: '用例标签',
    //   dataIndex: 'tags',
    // },
    // {
    //   title: '创建人',
    //   dataIndex: 'creator',
    //   width: 80,
    // },
    // {
    //   title: '创建时间',
    //   dataIndex: 'created_time',
    //   render: (_, record) => formatDateTimeByString(record.created_time),
    //   width: 170,
    // },
    {
      title: '操作',
      key: 'action',
      width: 150,
      render: (_, record) => (
        <Space size="middle">
          <a onClick={() => onCopy(record)}>复制</a>
          <a onClick={() => onEdit(record)}>编辑</a>
          <ExDeleteButton
            id={record.id}
            API={Api.complexReasoningCase.del}
            onSuccess={() => tableRef.current?.refresh()}
          />
        </Space>
      ),
    },
  ]

  const onAdd = () => {
    setFormData({ dataset_id, context_config: {} })
    setOpen(true)
  }

  const onEdit = (record: ComplexReasoningCase) => {
    setFormData(record)
    setOpen(true)
  }

  const onCopy = (record: ComplexReasoningCase) => {
    setFormData(removeMetaFields(record))
    setOpen(true)
  }

  const onImport = () => {
    setImportOpen(true)
  }

  const onExport = () => {
    setExportOpen(true)
  }

  const handleExportConfirm = () => {
    const dataset = datasetOptions.find((item) => item.value === dataset_id)?.label || dataset_id
    if (exportFormat === 'excel') {
      exportExcelGet('/complex_reasoning_case/export_excel', { dataset_id: dataset_id || '' }, `${dataset}.xlsx`)
    } else {
      exportJsonGet('/complex_reasoning_case/export', { dataset_id: dataset_id || '' }, `${dataset}.json`)
    }
    setExportOpen(false)
  }

  const handleSuccess = () => {
    tableRef.current?.refresh()
    setOpen(false)
    setImportOpen(false)
  }

  return (
    <>
      <ExTable<ComplexReasoningCase>
        ref={tableRef}
        params={params}
        columns={columns}
        api={Api.complexReasoningCase.page}
        searchProps={{
          searchList: searchList,
          action: (
            <>
              <Button
                type="primary"
                disabled={!buildParams.dataset_item_ids?.length}
                onClick={() => setOpenBuild(true)}
              >
                构建数据集
              </Button>
              <Button type="primary" onClick={onAdd}>
                新增
              </Button>
              <Button type="primary" onClick={onImport}>
                导入
              </Button>
              <Button type="primary" onClick={onExport}>
                导出
              </Button>
            </>
          ),
        }}
        tableProps={{
          rowSelection: {
            columnWidth: 50,
            selectedRowKeys: buildParams.dataset_item_ids,
            onChange: (selectedRowKeys) =>
              setBuildParams((prev) => ({ ...prev, dataset_item_ids: selectedRowKeys as string[] })),
          },
        }}
      />

      <ExDrawer open={open} setOpen={setOpen} title={formData.id ? '编辑测试用例' : '新增测试用例'}>
        <Form formData={formData} onCancel={() => setOpen(false)} onSuccess={handleSuccess} />
      </ExDrawer>

      <ExDrawer open={importOpen} setOpen={setImportOpen} title="导入测试用例">
        <Import
          action="/complex_reasoning_case/import"
          templates={[
            { url: '/template/complex_reasoning_case.json', name: 'JSON模板' },
            { url: '/template/dataset_import.xlsx', name: 'Excel模板' },
          ]}
          params={{ dataset_id }}
          onCancel={() => setImportOpen(false)}
          onSuccess={handleSuccess}
        />
      </ExDrawer>

      <Modal
        title="选择导出格式"
        open={exportOpen}
        onOk={handleExportConfirm}
        onCancel={() => setExportOpen(false)}
        okText="确定"
        cancelText="取消"
        destroyOnHidden
      >
        <Radio.Group value={exportFormat} onChange={(e) => setExportFormat(e.target.value)}>
          <Radio value="json">JSON</Radio>
          <Radio value="excel">Excel</Radio>
        </Radio.Group>
      </Modal>

      <ExDrawer open={openBuild} setOpen={setOpenBuild} title="构建数据集">
        <BuildForm
          formData={buildParams}
          setFormData={setBuildParams}
          onSuccess={() => {
            setBuildParams({ dataset_item_ids: [] })
            setOpenBuild(false)
          }}
          onCancel={() => {
            setOpenBuild(false)
          }}
        />
      </ExDrawer>
    </>
  )
}

export default App
