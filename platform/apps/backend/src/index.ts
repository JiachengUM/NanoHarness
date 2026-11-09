import { connect } from '@eval-platform/database'
import { buildApp } from './core/app'
import { logger } from '@eval-platform/shared'
import { getMongoUri, getPort, getHost } from './core/config'

async function main() {
  const MONGO_URI = getMongoUri()
  const PORT = getPort()
  const HOST = getHost()

  await connect(MONGO_URI)
  logger.info(`[database] connected to ${MONGO_URI}`)

  const app = await buildApp()
  await app.listen({ port: PORT, host: HOST })
}

main().catch((err) => {
  console.error('[fatal]', err)
  process.exit(1)
})
