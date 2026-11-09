import { useCallback, useEffect, useState } from 'react'
import { listToTree } from '@/utils/tree-list'

interface Option extends Common {
  children?: Option[]
}

export const useOptions = <T>(
  api: (p?: T) => Promise<T[]>,
  params?: T,
  format?: (item: T, index: number) => OptionItem<string> | string | undefined,
  toTree = false
): [OptionItem<string>[], () => void] => {
  const [searchParams, setSearchParams] = useState<T | undefined>()
  const [options, setOptions] = useState<OptionItem<string>[]>([])

  const load = useCallback(
    (params?: T) => {
      api(params || searchParams).then((res) => {
        const loop = (items: Option[]): OptionItem<string>[] => {
          return items.map((item, index) => {
            let optionItem: OptionItem<string> = {
              label: item.name as string,
              value: item.id,
              data: item,
            }

            if (format) {
              const formatted = format(item as T, index)
              if (typeof formatted === 'object') {
                optionItem = { ...optionItem, ...formatted }
              } else if (typeof formatted === 'string') {
                optionItem.label = formatted
              }
            }

            if (item.children?.length) {
              optionItem.children = loop(item.children)
            }

            return optionItem
          })
        }

        const _list = toTree ? listToTree((res as Option[]) || []) : res || []

        setOptions(loop(_list as Option[]))
      })
    },
    [api, format, toTree, searchParams]
  )

  useEffect(() => {
    const paramsStr = JSON.stringify(params)
    const searchParamsStr = JSON.stringify(searchParams)

    if (paramsStr === searchParamsStr) return

    setSearchParams(params)
    load(params)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params])

  useEffect(() => {
    setSearchParams(params)
    load(params)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return [options, load]
}

export const useTreeOptions = <T extends Common & { children?: T[] }>(
  api: (p?: T) => Promise<T[]>,
  params?: T,
  format?: (item: T) => string
): [OptionItem[], () => void] => {
  return useOptions<T>(api, params, format, true)
}
