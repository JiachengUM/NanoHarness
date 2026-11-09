import type { QueryFilter, HydratedDocument } from 'mongoose'
import { Types } from 'mongoose'
import { BaseRepository, type ListParams, type PageResult } from '../../base/repository'
import { ScenarioDoc, ScenarioModel } from './scenario.schema'
import type {
  CreateScenarioDto,
  UpdateScenarioDto,
  ListScenarioDto,
  PageScenarioDto,
  OutScenarioDto,
  BatchCreateScenarioDto,
  BatchUpdateScenarioDto,
  BatchDeleteScenarioDto,
} from './scenario.dto'
import { generationTaskRunRepository } from '../generation-task-run'

export class ScenarioRepository extends BaseRepository<
  ScenarioDoc,
  OutScenarioDto,
  CreateScenarioDto,
  UpdateScenarioDto
> {
  constructor() {
    super(ScenarioModel)
  }

  protected toDto(doc: HydratedDocument<ScenarioDoc>): OutScenarioDto {
    return {
      ...doc.toObject(),
      tag_tree_id: doc.tag_tree_id?.toString(),
      generation_task_id: doc.generation_task_id?.toString(),
      scenario_plan_id: doc.scenario_plan_id?.toString(),
    }
  }

  private async buildFilter(dto?: ListScenarioDto | PageScenarioDto): Promise<QueryFilter<ScenarioDoc>> {
    const filter: QueryFilter<ScenarioDoc> = {}

    if (dto?.keyword?.trim()) {
      const keyword = dto.keyword.trim()
      filter.$or = [
        { scenario_id: { $regex: this.escapeRegex(keyword), $options: 'i' } },
        { scenario_name: { $regex: this.escapeRegex(keyword), $options: 'i' } },
        { description: { $regex: this.escapeRegex(keyword), $options: 'i' } },
      ]
    }

    if (dto?.tag?.trim()) {
      filter.tags = { $regex: this.escapeRegex(dto.tag.trim()), $options: 'i' }
    }

    if (dto?.tag_tree_id?.trim()) {
      filter.tag_tree_id = dto.tag_tree_id.trim()
    }

    if (dto?.generation_task_id?.trim()) {
      filter.generation_task_id = dto.generation_task_id.trim()
    }

    if (dto?.generation_task_run_id?.trim()) {
      const scenarioPlan = await generationTaskRunRepository.findOne({
        generation_task_run_id: dto.generation_task_run_id.trim(),
      })

      if (scenarioPlan) filter.scenario_plan_id = scenarioPlan.id
    }

    if (dto?.scenario_plan_id?.trim()) {
      filter.scenario_plan_id = dto.scenario_plan_id.trim()
    }

    return filter
  }

  // ── CRUD ─────────────────────────────────────────────────────────────────

  async createScenario(dto: CreateScenarioDto): Promise<OutScenarioDto> {
    return this.create(dto)
  }

  async findByScenarioId(scenarioId: string): Promise<OutScenarioDto | null> {
    return this.findOne({ scenario_id: scenarioId })
  }

  async updateScenario(id: string | Types.ObjectId, dto: UpdateScenarioDto): Promise<OutScenarioDto | null> {
    return this.updateById(id, dto)
  }

  async deleteScenario(id: string | Types.ObjectId): Promise<boolean> {
    return this.deleteById(id)
  }

  // ── 批量操作 ─────────────────────────────────────────────────────────────

  async batchCreateScenarios(dto: BatchCreateScenarioDto): Promise<OutScenarioDto[]> {
    return this.createMany(dto.items)
  }

  async batchUpdateScenarios(dto: BatchUpdateScenarioDto): Promise<number> {
    const writes = dto.items.map((item) => {
      const { id, ...updateData } = item
      return {
        updateOne: {
          filter: { _id: new Types.ObjectId(id) },
          update: { $set: updateData },
        },
      }
    })
    const result = await this.model.bulkWrite(writes)
    return result.modifiedCount
  }

  async batchDeleteScenarios(dto: BatchDeleteScenarioDto): Promise<number> {
    const objectIds = dto.ids.map((id) => new Types.ObjectId(id))
    return this.deleteMany({ _id: { $in: objectIds } } as QueryFilter<ScenarioDoc>)
  }

  // ── 列表（不分页） ───────────────────────────────────────────────────────

  async listScenarios(dto?: ListScenarioDto): Promise<OutScenarioDto[]> {
    const params: ListParams<ScenarioDoc> = { filter: await this.buildFilter(dto) }
    return this.list(params)
  }

  // ── 分页 ──────────────────────────────────────────────────────

  async pageScenarios(dto?: PageScenarioDto): Promise<PageResult<OutScenarioDto>> {
    const { page = 1, page_size = 10 } = dto || {}
    const filter = await this.buildFilter(dto)
    return this.page({ ...filter, page, page_size })
  }
}

export const scenarioRepository = new ScenarioRepository()
