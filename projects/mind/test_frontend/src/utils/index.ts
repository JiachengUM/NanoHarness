export function getLabelById(id?: string | number | boolean, options?: OptionItem[], defaultLabel = ''): string {
  if (id == null || !options?.length) return defaultLabel

  return options.find((option) => option.value === id)?.label || defaultLabel
}

export function getTreeLabelById(id?: string | number | boolean, treeOptions?: OptionItem[], last = false): string {
  if (id == null || !treeOptions?.length) return ''

  const loop = (arr: OptionItem[], parents: string[] = []): string[] => {
    if (!arr) return parents

    for (const item of arr) {
      if (item.value === id) return [...parents, item.label || '']

      if (item.children) {
        const res = loop(item.children, [...parents, item.label || ''])

        if (res.length) return res
      }
    }

    return []
  }

  const labels = loop(treeOptions || []) || []

  if (last) return labels[labels.length - 1] || ''

  return labels.join('/')
}

export function getLabelsByIds(
  ids: string[] | number[] | boolean[] = [],
  options?: OptionItem[],
  join: string = '，'
): string {
  if (!ids?.length || !options?.length) return ''

  const labels = ids.map((id) => options.find((option) => option.value === id)?.label || '').filter((label) => label)

  return labels.join(join)
}

export const filterOption = (input: string, option?: OptionItem & { filterLabel?: string }) => {
  const label = option?.filterLabel || option?.label || ''
  if (typeof label !== 'string') return false
  return label.toLowerCase().includes(input.toLowerCase())
}

export const deleteNullKeys = <T extends Record<string, any> | Record<string, any>[]>(obj: T): T => {
  if (Array.isArray(obj)) {
    return obj
      .map((item) => (typeof item === 'object' && item !== null ? deleteNullKeys(item) : item))
      .filter((item) => item !== null && item !== undefined && item !== '') as T
  } else if (typeof obj === 'object' && obj !== null) {
    const newObj: Record<string, any> = {}
    Object.keys(obj).forEach((key) => {
      const value = obj[key]
      if (value !== null && value !== undefined && value !== '') {
        newObj[key] = typeof value === 'object' ? deleteNullKeys(value) : value
      }
    })
    return newObj as T
  }
  return obj
}
