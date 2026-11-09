import { prop, modelOptions, getModelForClass } from '@typegoose/typegoose'
import { BaseDocument } from '../../base/document'
import { createModelOptions } from '../../base/schema-options'

@modelOptions(createModelOptions('generation_task'))
export class GenerationTask extends BaseDocument {
  @prop({ required: true, trim: true })
  name!: string

  @prop()
  description?: string
}

export const GenerationTaskModel = getModelForClass(GenerationTask)
