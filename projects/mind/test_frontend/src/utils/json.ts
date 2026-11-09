export const stringToJson = (data: unknown, defaultValue = null) => {
  if (typeof data !== 'string') return data

  try {
    return JSON.parse(data)
  } catch {
    return defaultValue
  }
}

export const jsonToString = (data: unknown, defaultValue = '') => {
  if (!data) return ''

  if (typeof data === 'string') return data

  try {
    return JSON.stringify(data, null, 2)
  } catch {
    return defaultValue
  }
}

export const removeMetaFields = <T extends Common>(data: T): T => {
  const _data = { ...data }
  delete _data.created_time
  delete _data.updated_time
  delete _data.creator
  delete _data.id

  return _data as T
}

export const jsonRender = (data: unknown) => {
  if (!data) return data as string

  const _data = removeMetaFields(data as Common)

  return JSON.stringify(_data)
}

export const isJson = (str?: string) => {
  if (typeof str !== 'string') return false

  try {
    const result = JSON.parse(str)
    const type = Object.prototype.toString.call(result)
    return type === '[object Object]' || type === '[object Array]'
  } catch {
    return false
  }
}
