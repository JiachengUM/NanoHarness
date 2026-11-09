import dayjs from 'dayjs'

export const formatDateBySeconds = (timestamp: number | string): string => {
  if (!timestamp) return ''

  return dayjs(Number(timestamp) * 1000).format('YYYY-MM-DD')
}

export const formatDateTimeBySeconds = (timestamp: number): string => {
  if (!timestamp) return ''

  return dayjs(timestamp * 1000).format('YYYY-MM-DD HH:mm:ss')
}

export const formatDateTimeByString = (dateStr?: string): string => {
  if (!dateStr) return ''

  return dayjs(dateStr).format('YYYY-MM-DD HH:mm:ss')
}

export const formatDateByString = (dateStr?: string): string => {
  if (!dateStr) return ''

  return dayjs(dateStr).format('YYYY-MM-DD')
}

export const numberFormat = (num?: number, fixed = 2): string => {
  if (num == null || isNaN(num)) return ''
  if (typeof num !== 'number') num = Number(num)

  return +num.toFixed(fixed) + ''
}

export const percentFormat = (num?: number, fixed = 2, unit = ''): string => {
  if (num == null || isNaN(num)) return ''

  const _number = typeof num === 'number' ? num : Number(num)

  if (_number > 1) return numberFormat(_number, fixed) + unit

  return numberFormat(_number * 100, fixed) + unit
}

// 删除审计字段
export const removeAuditFields = <T>(
  data: T,
  fields: string[] = [],
  auditFields = ['created_time', 'updated_time', 'id', 'creator']
): T => {
  const _data = { ...data }
  const allFields = [...fields, ...auditFields]
  allFields.forEach((field) => {
    delete _data[field as keyof T]
  })
  return _data
}
