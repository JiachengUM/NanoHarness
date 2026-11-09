import type { QueryFilter, HydratedDocument } from 'mongoose'
import { Types } from 'mongoose'
import { BaseRepository, type PageResult } from '../../base/repository'
import { DatasetItem, DatasetItemModel } from './dataset-item.schema'
import type {
  CreateDatasetItemDto,
  UpdateDatasetItemDto,
  ListDatasetItemDto,
  PageDatasetItemDto,
  OutDatasetItemDto,
} from './dataset-item.dto'
import { datasetRepository } from '../dataset/dataset.repository'

export class DatasetItemRepository extends BaseRepository<
  DatasetItem,
  OutDatasetItemDto,
  CreateDatasetItemDto,
  UpdateDatasetItemDto
> {
  constructor() {
    super(DatasetItemModel)
  }

  protected toDto(doc: HydratedDocument<DatasetItem>): OutDatasetItemDto {
    return {
      ...doc.toObject(),
      dataset_id: doc.dataset_id.toString(),
    } as OutDatasetItemDto
  }

  private buildFilter(dto: ListDatasetItemDto): QueryFilter<DatasetItem> {
    const filter: QueryFilter<DatasetItem> = {}

    if (dto.dataset_id) {
      filter.dataset_id = dto.dataset_id
    }

    if (dto.source_scenario_id) {
      filter.source_scenario_id = dto.source_scenario_id
    }

    if (dto.keyword) {
      filter.$or = [
        { case_id: { $regex: dto.keyword, $options: 'i' } },
        { 'user_query_lists.content': { $regex: dto.keyword, $options: 'i' } },
        { expected_script: { $regex: dto.keyword, $options: 'i' } },
        { case_description: { $regex: dto.keyword, $options: 'i' } },
        { nl_assertion: { $regex: dto.keyword, $options: 'i' } },
        { tags: { $regex: dto.keyword, $options: 'i' } },
      ]
    }

    return filter
  }

  // ── 基于 DTO 的 CRUD ─────────────────────────────────────────────────────

  async createDatasetItem(dto: CreateDatasetItemDto): Promise<OutDatasetItemDto> {
    const result = await this.create(dto)
    await datasetRepository.updateDatasetItemCount(dto.dataset_id)
    return result
  }

  async updateDatasetItem(id: string | Types.ObjectId, dto: UpdateDatasetItemDto): Promise<OutDatasetItemDto | null> {
    return this.updateById(id, dto)
  }

  async deleteDatasetItem(id: string | Types.ObjectId): Promise<boolean> {
    const datasetItem = await this.findById(id)
    const ok = await this.deleteById(id)
    if (ok && datasetItem) await datasetRepository.updateDatasetItemCount(datasetItem.dataset_id)
    return ok
  }

  // ── 删除某个 dataset 下的所有 items ────────────────────────────────────

  async deleteByDatasetId(datasetId: string): Promise<number> {
    return this.deleteMany({ dataset_id: datasetId })
  }

  // ── 列表（不分页） ───────────────────────────────────────────────────────

  async listDatasetItems(dto: ListDatasetItemDto): Promise<OutDatasetItemDto[]> {
    const filter = this.buildFilter(dto)
    return this.list({ filter })
  }

  // ── 分页 ──────────────────────────────────────────────────────

  async pageDatasetItems(dto: PageDatasetItemDto): Promise<PageResult<OutDatasetItemDto>> {
    const { page = 1, page_size = 10 } = dto
    const filter = this.buildFilter(dto)
    return this.page({ ...filter, page, page_size })
  }
}

export const datasetItemRepository = new DatasetItemRepository()
