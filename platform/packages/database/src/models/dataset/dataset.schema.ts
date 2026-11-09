import { prop, modelOptions, getModelForClass } from '@typegoose/typegoose'
import { BaseDocument } from '../../base/document'
import { createModelOptions } from '../../base/schema-options'

// ── Typegoose 模型类 ───────────────────────────────────────────────────────

@modelOptions(createModelOptions('complex_reasoning_dataset'))
export class Dataset extends BaseDocument {
  @prop({ required: true, trim: true })
  name!: string

  @prop()
  description?: string

  @prop({ default: 0, min: 0 })
  item_count!: number
}

// ── Mongoose 模型 ─────────────────────────────────────────────────────────

export const DatasetModel = getModelForClass(Dataset)
