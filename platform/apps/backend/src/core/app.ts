import Fastify, { type FastifyInstance, type FastifyServerOptions, type FastifyError } from 'fastify'
import sensible from '@fastify/sensible'
import fastifySwagger from '@fastify/swagger'
import fastifySwaggerUI from '@fastify/swagger-ui'
import { ZodTypeProvider, serializerCompiler, validatorCompiler, jsonSchemaTransform } from 'fastify-type-provider-zod'
import { generateId } from '@eval-platform/shared'
import { registerRoutes } from '../api/register-routes'
import { registerResponseHelpers } from '../http/response'
import { HTTP_STATUS } from '../constants/http-status'
import { API_PREFIX } from '../constants'
import { createLoggerConfig } from '@eval-platform/shared'

export interface BuildAppOptions {
  logger?: FastifyServerOptions['logger']
}

export async function buildApp(options?: BuildAppOptions): Promise<FastifyInstance> {
  const app = Fastify({
    genReqId: () => generateId(),
    logger: options?.logger ?? createLoggerConfig(),
  }).withTypeProvider<ZodTypeProvider>()

  // ── 全局插件 ────────────────────────────────────────────────────────────

  await app.register(sensible)
  registerResponseHelpers(app)

  app.setValidatorCompiler(validatorCompiler)
  app.setSerializerCompiler(serializerCompiler)

  app.setNotFoundHandler((req, reply) => {
    reply.fail('Route not found', { statusCode: HTTP_STATUS.NOT_FOUND })
  })

  app.setErrorHandler((error, req, reply) => {
    const err = error as FastifyError
    const statusCode = err.statusCode ?? HTTP_STATUS.INTERNAL_SERVER_ERROR

    if (statusCode >= HTTP_STATUS.INTERNAL_SERVER_ERROR) {
      req.log.error({ err: error }, 'Unhandled server error')
    }

    const message = statusCode >= HTTP_STATUS.INTERNAL_SERVER_ERROR ? 'Internal Server Error' : err.message

    reply.fail(message, { statusCode })
  })

  // ── Swagger 文档 ─────────────────────────────────────────────────────────

  await app.register(fastifySwagger, {
    openapi: {
      info: {
        title: 'Agent Eval Platform Backend',
        description: 'Backend service for Agent Eval Platform',
        version: '1.0.0',
      },
      servers: [],
    },
    transform: jsonSchemaTransform,
  })

  await app.register(fastifySwaggerUI, {
    routePrefix: '/documentation',
  })

  // ── 健康检查 ─────────────────────────────────────────────────────────────

  app.get('/health', async (req, reply) => reply.success({ status: 'server is ok' }))

  // ── 业务路由 ─────────────────────────────────────────────────────────────

  await registerRoutes(app, { prefix: API_PREFIX })

  return app
}
