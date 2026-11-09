import type { QueryFilter } from 'mongoose'
import { Types } from 'mongoose'
import { BaseRepository, type ListParams, type PageResult } from '../../base/repository'
import { TagTreeDoc, TagTreeModel } from './tag-tree.schema'
import type { CreateTagTreeDto, UpdateTagTreeDto, ListTagTreeDto, PageTagTreeDto, OutTagTreeDto } from './tag-tree.dto'

export class TagTreeRepository extends BaseRepository<TagTreeDoc, OutTagTreeDto, CreateTagTreeDto, UpdateTagTreeDto> {
  constructor() {
    super(TagTreeModel)
  }

  private buildFilter(dto?: ListTagTreeDto): QueryFilter<TagTreeDoc> {
    const filter: QueryFilter<TagTreeDoc> = {}

    if (dto?.name?.trim()) filter.name = { $regex: this.escapeRegex(dto.name.trim()), $options: 'i' }

    return filter
  }

  async createTagTree(dto: CreateTagTreeDto): Promise<OutTagTreeDto> {
    return this.create(dto)
  }

  async findByName(name: string): Promise<OutTagTreeDto | null> {
    return this.findOne({ name })
  }

  async listTagTrees(dto?: ListTagTreeDto): Promise<OutTagTreeDto[]> {
    const params: ListParams<TagTreeDoc> = { filter: this.buildFilter(dto) }
    return this.list(params)
  }

  async pageTagTrees(dto?: PageTagTreeDto): Promise<PageResult<OutTagTreeDto>> {
    const { page = 1, page_size = 10 } = dto || {}
    const filter = this.buildFilter(dto)
    return this.page({ ...filter, page, page_size })
  }

  async updateTagTree(id: string | Types.ObjectId, dto: UpdateTagTreeDto): Promise<OutTagTreeDto | null> {
    return this.updateById(id, dto)
  }

  async deleteTagTree(id: string | Types.ObjectId): Promise<boolean> {
    return this.deleteById(id)
  }
}

export const tagTreeRepository = new TagTreeRepository()
