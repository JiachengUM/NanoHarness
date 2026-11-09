import { QueryFilter, HydratedDocument, Model, SortOrder, Types } from 'mongoose'
import type { BaseDocument } from './document'

// ── 参数 / 返回类型 ─────────────────────────────────────────────────────────

export interface ListParams<T> {
  filter?: QueryFilter<T> // 过滤条件
  sort?: Record<string, SortOrder> // 排序规则，默认为 { updated_time: -1 }
  limit?: number // 限制返回数量，默认为 0（不限制）
  skip?: number // 跳过前 N 条，默认为 0（不跳过）
}

export interface PageParams {
  page: number // 页码，从 1 开始
  page_size: number // 每页数量，必须大于 0
}

export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

// ── 基础仓储 ───────────────────────────────────────────────────────────────

export abstract class BaseRepository<
  T extends BaseDocument,
  OutDto = HydratedDocument<T>,
  CreateDto = Partial<T>,
  UpdateDto = Partial<T>,
> {
  constructor(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    protected readonly model: Model<any>,
  ) {}

  protected toDto(doc: HydratedDocument<T>): OutDto {
    return doc.toObject() as unknown as OutDto
  }

  /** 转义正则表达式中的特殊字符。 */
  protected escapeRegex(input: string): string {
    return input.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  }

  protected objectId(id?: string): Types.ObjectId | undefined {
    if (!id) return undefined
    return new Types.ObjectId(id)
  }

  /** 根据 _id 查询单条文档。 */
  async findById(id: string | Types.ObjectId): Promise<OutDto | null> {
    const doc = await this.model.findById(id).exec()
    return doc ? this.toDto(doc) : null
  }

  /** 根据过滤条件查询一条文档。 */
  async findOne(filter: QueryFilter<T>): Promise<OutDto | null> {
    const doc = await this.model.findOne(filter).exec()
    return doc ? this.toDto(doc) : null
  }

  /** 新增一条文档。 */
  async create(data: CreateDto): Promise<OutDto> {
    const doc = await this.model.create(data as unknown as Partial<T>)
    return this.toDto(doc)
  }

  /** 批量新增文档。 */
  async createMany(data: CreateDto[]): Promise<OutDto[]> {
    const docs = await this.model.insertMany(data as unknown as Partial<T>[])
    return docs.map((doc) => this.toDto(doc as HydratedDocument<T>))
  }

  /** 根据 _id 更新文档并返回更新后的文档（不存在则为 null）。 */
  async updateById(id: string | Types.ObjectId, data: UpdateDto): Promise<OutDto | null> {
    const doc = await this.model
      .findByIdAndUpdate(id, { $set: data as unknown as Partial<T> }, { new: true, runValidators: true })
      .exec()
    return doc ? this.toDto(doc) : null
  }

  /** 根据过滤条件更新一条文档并返回更新后的文档（不存在则为 null）。 */
  async updateOne(filter: QueryFilter<T>, data: UpdateDto): Promise<OutDto | null> {
    const doc = await this.model
      .findOneAndUpdate(filter, { $set: data as unknown as Partial<T> }, { new: true, runValidators: true })
      .exec()
    return doc ? this.toDto(doc) : null
  }

  /** 根据过滤条件批量更新文档，返回被修改的文档数量。 */
  async updateMany(filter: QueryFilter<T>, data: UpdateDto): Promise<number> {
    const result = await this.model
      .updateMany(filter, { $set: data as unknown as Partial<T> }, { runValidators: true })
      .exec()
    return result.modifiedCount
  }

  /** 根据 _id 删除文档，成功删除返回 true。 */
  async deleteById(id: string | Types.ObjectId): Promise<boolean> {
    const result = await this.model.findByIdAndDelete(id).exec()
    return result !== null
  }

  /** 根据过滤条件删除一条文档，成功删除返回 true。 */
  async deleteOne(filter: QueryFilter<T>): Promise<boolean> {
    const result = await this.model.findOneAndDelete(filter).exec()
    return result !== null
  }

  /** 根据过滤条件批量删除文档，返回删除数量。 */
  async deleteMany(filter: QueryFilter<T>): Promise<number> {
    const result = await this.model.deleteMany(filter).exec()
    return result.deletedCount ?? 0
  }

  /** 返回全部匹配文档（完整列表，不分页）。 */
  async list(params: ListParams<T> = {}): Promise<OutDto[]> {
    const { filter = {}, sort = { updated_time: -1 }, limit, skip } = params
    const docs = await this.model
      .find(filter)
      .sort(sort)
      .skip(skip ?? 0)
      .limit(limit ?? 0)
      .exec()
    return docs.map((doc) => this.toDto(doc))
  }

  /** 统计匹配文档数量。 */
  async count(filter: QueryFilter<T> = {}): Promise<number> {
    return this.model.countDocuments(filter).exec()
  }

  /** 返回一页结果。 */
  async page(params: QueryFilter<T> & PageParams = { page: 1, page_size: 10 }): Promise<PageResult<OutDto>> {
    const { page, page_size, ...filter } = params
    const skip = (page - 1) * page_size

    const [items, total] = await Promise.all([
      this.model.find(filter).sort({ updated_time: -1 }).skip(skip).limit(page_size).exec(),
      this.model.countDocuments(filter).exec(),
    ])

    return {
      items: items.map((doc) => this.toDto(doc)),
      total,
      page,
      page_size,
      pages: Math.ceil(total / page_size),
    }
  }
}
