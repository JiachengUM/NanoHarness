import { prop, modelOptions, getModelForClass } from '@typegoose/typegoose'
import { Schema, Types } from 'mongoose'
import { BaseDocument } from '../../base/document'
import { createModelOptions } from '../../base/schema-options'

// ═══════════════════════════════════════════════════════════════════════════
// 场景 MongoDB 模型
// ═══════════════════════════════════════════════════════════════════════════

@modelOptions(createModelOptions('scenario'))
export class ScenarioDoc extends BaseDocument {
  /** 关联的场景生成计划 ID */
  @prop({ type: () => Schema.Types.ObjectId })
  scenario_plan_id?: Types.ObjectId

  /** 场景 ID（业务唯一标识） */
  @prop({ required: true, trim: true, unique: true })
  scenario_id!: string

  /** 场景名称 */
  @prop({ required: true, trim: true })
  scenario_name!: string

  /** 场景描述 */
  @prop({ required: true, trim: true })
  description!: string

  /** 标签列表 */
  @prop({ type: () => [String], required: true })
  tags!: string[]

  /** 该场景归属的场景模式（由 Pattern Generator 生成时填充） */
  @prop({ trim: true })
  pattern?: string

  /** 关联的标签树 ID（可选） */
  @prop({ type: () => Schema.Types.ObjectId })
  tag_tree_id?: Types.ObjectId

  /** 来源 query（记录生成该场景的原始 query） */
  @prop()
  source_query?: string

  /** 关联的生成任务 ID */
  @prop({ type: () => Schema.Types.ObjectId })
  generation_task_id?: Types.ObjectId
}

// ═══════════════════════════════════════════════════════════════════════════
// Mongoose 模型
// ═══════════════════════════════════════════════════════════════════════════

export const ScenarioModel = getModelForClass(ScenarioDoc)
