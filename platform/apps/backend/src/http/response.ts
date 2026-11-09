import type { FastifyReply, FastifyRequest } from 'fastify'
import { HTTP_STATUS } from '../constants/http-status'

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
  trace_id: string
}

export interface SendResponseOptions {
  statusCode?: number
  code?: number
  message?: string
}

declare module 'fastify' {
  interface FastifyReply {
    success<T>(data: T, options?: SendResponseOptions): FastifyReply
    fail(message: string, options?: SendResponseOptions): FastifyReply
  }
}

export function registerResponseHelpers(app: FastifyRequest['server']) {
  app.decorateReply('success', function <T>(this: FastifyReply, data: T, options: SendResponseOptions = {}) {
    const statusCode = options.statusCode ?? HTTP_STATUS.OK
    const code = options.code ?? statusCode

    const payload: ApiResponse<T> = {
      code,
      message: options.message ?? '',
      data,
      trace_id: this.request.id,
    }

    return this.code(statusCode).send(payload)
  })

  app.decorateReply('fail', function (this: FastifyReply, message: string, options: SendResponseOptions = {}) {
    const statusCode = options.statusCode ?? HTTP_STATUS.INTERNAL_SERVER_ERROR
    const code = options.code ?? statusCode

    const payload: ApiResponse<null> = {
      code,
      message,
      data: null,
      trace_id: this.request.id,
    }

    return this.code(statusCode).send(payload)
  })
}
