import type { QueryFilter, HydratedDocument } from 'mongoose'
import { Types } from 'mongoose'
import { BaseRepository, type ListParams, type PageResult } from '../../base/repository'
import { Dataset, DatasetModel } from './dataset.schema'
import type { CreateDatasetDto, UpdateDatasetDto, ListDatasetDto, PageDatasetDto, OutDatasetDto } from './dataset.dto'
import { datasetItemRepository } from '../dataset-item'

export class DatasetRepository extends BaseRepository<Dataset, OutDatasetDto, CreateDatasetDto, UpdateDatasetDto> {
  constructor() {
    super(DatasetModel)
  }

  private buildFilter(dto?: ListDatasetDto | PageDatasetDto): QueryFilter<Dataset> {
    const filter: QueryFilter<Dataset> = {}

    if (dto?.name?.trim()) filter.name = { $regex: this.escapeRegex(dto.name.trim()), $options: 'i' }

    return filter
  }

  // ── 基于 DTO 的 CRUD ─────────────────────────────────────────────────────

  async createDataset(dto: CreateDatasetDto): Promise<OutDatasetDto> {
    return this.create(dto)
  }

  async updateDataset(id: string | Types.ObjectId, dto: UpdateDatasetDto): Promise<OutDatasetDto | null> {
    return this.updateById(id, dto)
  }

  async deleteDataset(id: string | Types.ObjectId, deleteItems: boolean = true): Promise<boolean> {
    if (deleteItems) await datasetItemRepository.deleteByDatasetId(id.toString())
    return this.deleteById(id)
  }

  // ── 列表（不分页） ───────────────────────────────────────────────────────

  async listDatasets(dto?: ListDatasetDto): Promise<OutDatasetDto[]> {
    const params: ListParams<Dataset> = { filter: this.buildFilter(dto) }
    const datasets = await this.list(params)
    await Promise.all(
      datasets.map(async (ds) => {
        const count = await datasetItemRepository.count({ dataset_id: ds.id })
        if (count !== ds.item_count) {
          await this.updateDataset(ds.id, { item_count: count })
        }
      }),
    )
    return datasets
  }

  // ── 分页 ──────────────────────────────────────────────────────

  async pageDatasets(dto?: PageDatasetDto): Promise<PageResult<OutDatasetDto>> {
    const { page = 1, page_size = 10 } = dto || {}
    const filter = this.buildFilter(dto)
    const result = await this.page({ ...filter, page, page_size })
    await Promise.all(
      result.items.map(async (ds) => {
        const count = await datasetItemRepository.count({ dataset_id: ds.id })
        if (count !== ds.item_count) {
          await this.updateDataset(ds.id, { item_count: count })
        }
      }),
    )
    return result
  }

  // ── 更新 dataset 下的 item 数量 ───────────────────────────────────────────

  async updateDatasetItemCount(datasetId: string): Promise<void> {
    const count = await datasetItemRepository.count({ dataset_id: datasetId })
    await this.updateById(datasetId, { item_count: count })
  }
}

export const datasetRepository = new DatasetRepository()
