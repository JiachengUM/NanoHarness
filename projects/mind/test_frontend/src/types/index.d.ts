declare module '*.svg?react' {
  export default React.FunctionComponent<React.SVGProps<SVGElement>>
}

type AnyObject = Record<PropertyKey, unknown>

interface ApiRes<T> {
  code: number
  message: string
  data: T
  traceId?: string
}

interface ApiError {
  errorCode: number
  message: string
  status: number
  timestamp: number
}

type PageParams<T> = {
  page?: number
  size?: number
} & T

interface PageList<T> {
  page: number
  size: number
  total: number
  items: T[]
}

interface OptionItem<T = string | number> {
  label?: string
  value?: T
  children?: OptionItem<T>[]
  [key: string]: unknown
}

interface Common extends AnyObject {
  id?: string
  created_time?: string
  creator?: string
  updated_time?: string
}

interface FeishuUser extends Common {
  open_id: string
  union_id?: string
  user_id?: string
  name: string
  avatar_url?: string
  email?: string
  mobile?: string
  tenant_key?: string
  last_login_at?: string
}
