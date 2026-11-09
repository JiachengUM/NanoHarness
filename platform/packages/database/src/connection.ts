import mongoose from 'mongoose'

let _connected = false

/** 连接 MongoDB。可安全重复调用：若已连接则直接跳过。 */
export async function connect(uri: string): Promise<void> {
  if (_connected) return
  await mongoose.connect(uri)
  _connected = true
}

/** 断开 MongoDB 连接。 */
export async function disconnect(): Promise<void> {
  if (!_connected) return
  await mongoose.disconnect()
  _connected = false
}

export { mongoose }
