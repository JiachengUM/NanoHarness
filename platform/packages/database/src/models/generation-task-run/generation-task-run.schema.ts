import { prop, modelOptions, getModelForClass } from '@typegoose/typegoose'
import { BaseDocument } from '../../base/document'
import { createModelOptions } from '../../base/schema-options'
import { Schema, Types } from 'mongoose'

@modelOptions(createModelOptions('generation_task_run'))
export class GenerationTaskRun extends BaseDocument {
  @prop({ required: true, type: () => Schema.Types.ObjectId })
  generation_task_id!: Types.ObjectId

  @prop({ required: true })
  query!: string

  @prop({ required: true, type: () => Schema.Types.ObjectId })
  tag_tree_id!: Types.ObjectId

  @prop({ default: '' })
  status!: string

  @prop()
  progress!: number

  @prop({ default: () => [] })
  events!: Record<string, unknown>[] // todo: 定义事件结构体
}

export const GenerationTaskRunModel = getModelForClass(GenerationTaskRun)
