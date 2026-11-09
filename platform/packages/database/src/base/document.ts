import { prop } from '@typegoose/typegoose'
import type { Types } from 'mongoose'

/**
 * 所有 Typegoose 文档的基类。
 * 声明 Mongoose 在运行时注入的 _id / id / 时间戳字段。
 * 子类通过 `@modelOptions({ schemaOptions: { timestamps: true } })`
 * 即可让 Mongoose 自动维护 created_time / updated_time。
 */
export abstract class BaseDocument {
  declare _id: Types.ObjectId
  declare id: string // Mongoose 虚拟字段
  declare created_time: Date // 由 { timestamps: true } 自动注入
  declare updated_time: Date

  @prop({ default: 'system', trim: true })
  creator!: string
}
