import { prop, modelOptions, getModelForClass } from '@typegoose/typegoose'
import { BaseDocument } from '../../base/document'
import { createModelOptions } from '../../base/schema-options'
import type { TagTree } from './tag-tree.dto'

// ═══════════════════════════════════════════════════════════════════════════
// 标签树 MongoDB 模型
// ═══════════════════════════════════════════════════════════════════════════

@modelOptions(createModelOptions('tag_tree'))
export class TagTreeDoc extends BaseDocument {
  /** 标签树名称（用于标识，如 vehicle-assistant-base） */
  @prop({ required: true, trim: true, unique: true })
  name!: string

  /** 标签树描述 */
  @prop()
  description?: string

  /** 完整的标签树数据（以 Mixed 存储 JSON 树结构） */
  @prop({ type: () => Object, required: true })
  tree!: TagTree
}

// ═══════════════════════════════════════════════════════════════════════════
// Mongoose 模型
// ═══════════════════════════════════════════════════════════════════════════

export const TagTreeModel = getModelForClass(TagTreeDoc)
