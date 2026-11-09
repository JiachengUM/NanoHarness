// const LOCAL_MONGO_URI = 'mongodb://127.0.0.1:27017/ai-mind-test'

const HUOSHAN_MONGO_URI =
  'REDACTED'

export function getMongoUri(): string {
  return process.env.MONGO_URI || HUOSHAN_MONGO_URI
}

export function getPort(): number {
  return Number(process.env.PORT) || 8100
}

export function getHost(): string {
  return process.env.HOST || '0.0.0.0'
}
