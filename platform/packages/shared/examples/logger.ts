import { logger } from '../src/logger'

/**
 * debug及以上等级的日志会被打印到控制台
 * info及以上等级的日志会被写入日志文件
 */
logger.silent('logger silent test 静默日志') // 不会被打印到控制台或日志文件
logger.trace('logger trace test 跟踪日志') // 不会被打印到控制台或日志文件
logger.debug('logger debug test 调试日志') // 会被打印到控制台，不会写入日志文件
logger.info('logger info test 信息日志') // 会被打印到控制台，也会写入日志文件
logger.warn('logger warn test 警告日志') // 会被打印到控制台，也会写入日志文件
logger.error('logger error test 错误日志') // 会被打印到控制台，也会写入日志文件
logger.fatal('logger fatal test 致命错误日志') // 会被打印到控制台，也会写入日志文件
