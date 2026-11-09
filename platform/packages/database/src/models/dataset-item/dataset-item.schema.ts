import { Severity, prop, modelOptions, getModelForClass } from '@typegoose/typegoose'
import { Schema, Types } from 'mongoose'
import { BaseDocument } from '../../base/document'
import { createModelOptions } from '../../base/schema-options'
import type { UserQuerySession } from './dataset-item.dto'
import { DEFAULT_MAX_ROUND } from './dataset-item.dto'

// ── Typegoose 模型类 ───────────────────────────────────────────────────────

@modelOptions({
  ...createModelOptions('complex_reasoning_case'),
  options: {
    allowMixed: Severity.ALLOW,
  },
})
export class DatasetItem extends BaseDocument {
  /** 所属 Dataset 的 _id */
  @prop({ required: true, type: () => Schema.Types.ObjectId })
  dataset_id!: Types.ObjectId

  /** 测试用例的唯一标识（同 dataset 内唯一） */
  @prop({ required: true, trim: true })
  case_id!: string

  /** 测试用例的上下文配置，自由 dict */
  @prop({ type: () => Object, default: {} })
  context_config!: Record<string, unknown>

  /** 最大对话轮数 */
  @prop({ default: DEFAULT_MAX_ROUND, min: 1 })
  max_round!: number

  /**
   * 多次「独立会话」列表，对应 Python user_query_lists。
   * 元素格式：
   *   1) 旧格式 Message[]（list[Message]）
   *   2) DialogueRoundConfig（含 mock_info / mock_time）
   * MongoDB 以 Mixed 数组存储，TypeScript 侧通过 UserQuerySession 约束。
   */
  @prop({ type: () => [Object], default: [] })
  user_query_lists!: UserQuerySession[]

  /** 预期的多次多轮对话文本描述，供模拟人及 judge 使用 */
  @prop({ default: '' })
  expected_script!: string

  /** 自然语言断言列表，由 LLM judge 判定是否通过 */
  @prop({ type: () => [String], default: [] })
  nl_assertion!: string[]

  /** 代码断言，key 为待验证变量名，value 为预期值 */
  @prop()
  code_assertion?: Record<string, unknown>

  /** 测试用例综合描述 */
  @prop()
  case_description?: string

  /** 标签列表 */
  @prop({ type: () => [String], default: [] })
  tags!: string[]

  /** 来源场景ID */
  @prop()
  source_scenario_id?: string

  /** 来源场景名称 */
  @prop()
  source_scenario_name?: string
}

// ── Mongoose 模型 ─────────────────────────────────────────────────────────

export const DatasetItemModel = getModelForClass(DatasetItem)
