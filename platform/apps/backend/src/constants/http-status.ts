export const HTTP_STATUS = {
  OK: 200, // 成功
  CREATED: 201, // 创建成功
  BAD_REQUEST: 400, // 请求错误
  UNAUTHORIZED: 401, // 未授权
  FORBIDDEN: 403, // 禁止访问
  NOT_FOUND: 404, // 未找到
  CONFLICT: 409, // 冲突
  UNPROCESSABLE_ENTITY: 422, // 无法处理的实体
  TOO_MANY_REQUESTS: 429, // 请求过多
  INTERNAL_SERVER_ERROR: 500, // 服务器内部错误
  BAD_GATEWAY: 502, // 网关错误
  SERVICE_UNAVAILABLE: 503, // 服务不可用
} as const

export type HttpStatusCode = (typeof HTTP_STATUS)[keyof typeof HTTP_STATUS]
