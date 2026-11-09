import { resolve } from 'node:path'
import pino from 'pino'

const LOG_DIR = resolve(process.cwd(), 'logs')

export function createLoggerConfig(packageName: string = 'app') {
  return {
    level: 'debug',
    transport: {
      targets: [
        {
          target: 'pino-pretty',
          level: 'debug',
          options: {
            colorize: true,
          },
        },
        {
          target: 'pino/file',
          level: 'info',
          options: {
            destination: resolve(LOG_DIR, `${packageName}.log`),
            mkdir: true,
          },
        },
      ],
    },
  }
}

export const logger = pino(createLoggerConfig())
