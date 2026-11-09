import { prop, modelOptions, getModelForClass } from '@typegoose/typegoose'
import { Schema, Types } from 'mongoose'
import { BaseDocument } from '../../base/document'
import { createModelOptions } from '../../base/schema-options'

/**
 * 单条硬约束（MongoDB 子文档）
 */
export class HardConstraintDoc {
  @prop({ required: true, enum: ['capability_required', 'capability_excluded', 'interaction_pattern', 'theme', 'difficulty', 'other'] })
  type!: 'capability_required' | 'capability_excluded' | 'interaction_pattern' | 'theme' | 'difficulty' | 'other'

  @prop({ required: true })
  description!: string
}

/**
 * 场景生成计划
 *
 * 将用户模糊 query 转换为结构化的生成计划。
 * 关联到 GenerationTask，便于追溯。
 */
@modelOptions(createModelOptions('scenario_plans'))
export class ScenarioPlanDoc extends BaseDocument {
  /**
   * 关联的生成任务 ID
   */
  @prop({ type: () => Schema.Types.ObjectId })
  task_id?: Types.ObjectId

  /**
   * 关联的生成任务运行 ID
   */
  @prop({ type: () => Schema.Types.ObjectId })
  generation_task_run_id?: Types.ObjectId

  /**
   * 用户原始 query
   */
  @prop({ required: true })
  original_query!: string

  /**
   * 改写后的详细任务描述
   * (给 Generator 和 Judge 使用的标准化描述)
   */
  @prop({ required: true })
  task_description!: string

  /**
   * 目标覆盖的标签列表
   */
  @prop({ type: () => [String], required: true })
  target_tags!: string[]

  /**
   * 对原始 query 的理解注解
   * (帮助用户确认需求理解是否正确)
   */
  @prop({ required: true })
  interpretation_notes!: string

  /**
   * 从 query 中提取的硬约束列表
   * 贯穿 Pattern Generator / 场景生成 / Judge 全链路
   */
  @prop({ type: () => [HardConstraintDoc], default: [] })
  hard_constraints!: HardConstraintDoc[]

  /**
   * 状态
   */
  @prop({ enum: ['pending', 'confirmed', 'generating', 'completed', 'cancelled'], default: 'pending' })
  status!: 'pending' | 'confirmed' | 'generating' | 'completed' | 'cancelled'

  /**
   * 标签树名称
   */
  @prop({ required: true })
  tag_tree_name!: string

  /**
   * 目标场景数（由 Pattern Generator 决定，用于进度计算）
   */
  @prop({ default: 0 })
  target_scenario_count?: number
}

export const ScenarioPlanModel = getModelForClass(ScenarioPlanDoc)
