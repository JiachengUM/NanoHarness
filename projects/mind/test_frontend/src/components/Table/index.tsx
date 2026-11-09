import React, { useCallback, useEffect, useMemo, useState, useImperativeHandle, useRef } from 'react'
import type { TableColumnsType, TablePaginationConfig, TableProps } from 'antd'
import AutoSizer from 'react-virtualized-auto-sizer'
import { Table } from 'antd'
import style from './index.module.less'
import Search from './search'
import type { Props as SearchProps } from './search'

export interface HandleType<P extends AnyObject = AnyObject, T = AnyObject> {
  refresh: () => void
  search: (values: P) => void
  setChildren: (pid: string, children: T[]) => void
  getPanination: () => TablePaginationConfig
}

export type ColumnsType<T> = (TableColumnsType<T>[number] & {
  type?: 'user' | 'dateTime'
})[]

export type Props<T, P> = {
  title?: React.ReactNode
  rowKey?: string
  height?: string
  columns?: ColumnsType<T>
  dataSource?: T[]
  api?: (params?: P) => Promise<T[] | PageList<T>>
  params?: P
  loading?: boolean
  header?: React.ReactNode
  action?: React.ReactNode
  table?: React.ReactNode
  intercept?: (res: T[]) => T[]
  tableProps?: TableProps<T>
  searchProps?: SearchProps
  paginationProps?: TablePaginationConfig
  headerHeight?: number
  onSearch?: (p: P) => void
}

const PAGE_SIZE = 10
const CURRENT = 1

const ExTable = <T extends AnyObject = AnyObject, P extends AnyObject = AnyObject>({
  ref,
  ...props
}: Props<T, P> & { ref?: React.Ref<HandleType<P, T>> }) => {
  const {
    title,
    rowKey = 'id',
    columns,
    params,
    header,
    loading,
    action,
    table,
    api,
    dataSource,
    intercept,
    tableProps,
    searchProps,
    paginationProps,
    onSearch,
    headerHeight = 55,
  } = props
  const [tableLoading, setTableLoading] = useState(false)
  const [tableDataSource, setTableDataSource] = useState<T[]>([])
  const [searchParams, setSearchParams] = useState<P>()
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [pagination, setPagination] = useState<TablePaginationConfig>({ current: CURRENT, pageSize: PAGE_SIZE })

  // 使用 ref 避免初始化时的重复请求
  const isInitialMount = useRef(true)

  const searchRequiredKeys = useMemo(() => {
    return searchProps?.searchList
      ?.filter((item) => {
        return item.required
      })
      .map((item) => item.key)
      .join(',')
  }, [searchProps?.searchList])

  const onChange = (p: TablePaginationConfig) => {
    if (p.current !== pagination.current || p.pageSize !== pagination.pageSize) {
      setPagination(p)
      fetchData(buildParams(p.current, p.pageSize, searchParams))
    }
  }

  const buildParams = useCallback(
    (pageNo = CURRENT, pageSize = PAGE_SIZE, searchParams = searchProps?.initialValues) => {
      return {
        page: pageNo,
        page_size: pageSize,
        ...params,
        ...searchParams,
      } as unknown as P
    },
    [params, searchProps?.initialValues]
  )

  const checkParams = useCallback(
    (params: P) => {
      if (!searchRequiredKeys) return true

      const keyArr = searchRequiredKeys.split(',')
      const needParams = keyArr.find((key) => {
        return params[key] === undefined || params[key] === ''
      })

      if (needParams) {
        // messageApi.error('请填写完整查询条件')
        return false
      }

      return true
    },
    [searchRequiredKeys]
  )

  const fetchData = useCallback(
    async (params: P) => {
      if (!api) return

      if (!checkParams(params)) return

      setTableLoading(true)
      console.log('params:', params)
      onSearch?.(params)
      try {
        const res = await api(params)
        const _intercept = intercept || ((res: T[]) => res)

        if (Array.isArray(res)) {
          setTableDataSource(_intercept(res))
        } else if (typeof res === 'object') {
          const list = res?.items || []
          const total = res?.total || 0
          setTableDataSource(_intercept(list))
          setPagination((prev) => ({ ...prev, total }))
        } else {
          setTableDataSource([])
          setPagination((prev) => ({ ...prev, total: 0 }))
        }
      } catch (e) {
        console.log(e)
      } finally {
        setTableLoading(false)
      }
    },
    [api, intercept, checkParams, onSearch]
  )

  const search = (values: P) => {
    setSearchParams(values)
    setPagination((prev) => ({ ...prev, current: CURRENT }))
    fetchData(buildParams(CURRENT, pagination.pageSize, values))
  }

  const refresh = () => {
    fetchData(buildParams(pagination.current, pagination.pageSize, searchParams))
  }

  const setChildren = (pid: string, children: T[]) => {
    setTableDataSource((prev) => {
      return prev.map((item) => {
        if (item[rowKey] === pid) {
          return { ...item, children }
        }

        return item
      })
    })
  }

  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false
      fetchData(buildParams())
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (api) return

    const _intercept = intercept || ((res: T[]) => res)

    setTableDataSource(_intercept(dataSource || []))
  }, [api, dataSource, intercept])

  useImperativeHandle(ref, () => ({
    refresh,
    search,
    getPanination: () => pagination,
    setChildren,
  }))

  const _tableProps: TableProps<T> = {
    rowKey,
    loading: tableLoading || loading,
    columns,
    pagination: {
      position: ['bottomLeft'],
      showTotal: (total: number) => `共 ${total} 条`,
      showQuickJumper: true,
      showSizeChanger: true,
      ...pagination,
      ...paginationProps,
    },
    dataSource: tableDataSource,
    onChange,
    ...tableProps,
    rowSelection: tableProps?.rowSelection && {
      ...tableProps?.rowSelection,
      onChange: (selectedRowKeys, ...otherProps) => {
        setSelectedRowKeys(selectedRowKeys)
        tableProps?.rowSelection?.onChange?.(selectedRowKeys, ...otherProps)
      },
    },
  }

  return (
    <>
      <div className={style.content} style={{ height: '100%' }}>
        <div className={style.header}>
          {title && <div className={style.title}>{title}</div>}
          {searchProps && (
            <Search loading={tableLoading || loading} onSearch={(e) => search(e as P)} {...searchProps} />
          )}
          {header}
        </div>
        {(!!action || selectedRowKeys.length > 0) && (
          <div className={style.action}>
            <div>{selectedRowKeys.length > 0 && <div>已选择 {selectedRowKeys.length} 项</div>}</div>

            <div style={{ marginLeft: 12 }}>{action}</div>
          </div>
        )}

        <div className={style.table} style={{ overflow: tableProps?.virtual ? 'hidden' : 'auto' }}>
          {table && table}
          {!table && tableProps?.virtual && (
            <AutoSizer>
              {({ height, width }) => {
                tableProps.scroll = tableProps.scroll || {}
                tableProps.scroll.y = height - (headerHeight + (tableProps?.pagination === false ? 0 : 45)) // headerHeight 为表头高度 45为分页高度
                return (
                  <div style={{ height, width }}>
                    <Table {..._tableProps} />
                  </div>
                )
              }}
            </AutoSizer>
          )}

          {!table && !tableProps?.virtual && <Table {..._tableProps} />}
        </div>
      </div>
    </>
  )
}

export default ExTable
