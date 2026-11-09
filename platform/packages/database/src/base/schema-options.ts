function transform(_doc: unknown, ret: Record<string, unknown>) {
  delete ret._id
  delete ret.__v
  return ret
}

/**
 * Typegoose 模型公共配置。
 * 确保所有 schema 使用统一的时间字段命名与 JSON/Object 序列化行为。
 */
export function createModelOptions(collection: string) {
  return {
    schemaOptions: {
      timestamps: {
        createdAt: 'created_time',
        updatedAt: 'updated_time',
      },
      versionKey: false as const,
      collection,
      toJSON: {
        virtuals: true,
        minimize: false,
        transform,
      },
      toObject: {
        virtuals: true,
        minimize: false,
        transform,
      },
    },
  }
}
