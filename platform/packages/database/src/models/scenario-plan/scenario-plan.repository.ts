import type { QueryFilter, HydratedDocument } from 'mongoose'
import { Types } from 'mongoose'
import { BaseRepository, PageResult } from '../../base/repository'
import { ScenarioPlanDoc, ScenarioPlanModel } from './scenario-plan.schema'
import type {
  CreateScenarioPlanDto,
  ListScenarioPlanDto,
  PageScenarioPlanDto,
  UpdateScenarioPlanDto,
  OutScenarioPlanDto,
} from './scenario-plan.dto'

export class ScenarioPlanRepository extends BaseRepository<
  ScenarioPlanDoc,
  OutScenarioPlanDto,
  CreateScenarioPlanDto,
  UpdateScenarioPlanDto
> {
  constructor() {
    super(ScenarioPlanModel)
  }

  protected toDto(doc: HydratedDocument<ScenarioPlanDoc>): OutScenarioPlanDto {
    return {
      ...doc.toObject(),
      task_id: doc.task_id?.toString(),
      generation_task_run_id: doc.generation_task_run_id?.toString(),
    }
  }

  private buildFilter(dto?: ListScenarioPlanDto | PageScenarioPlanDto): QueryFilter<ScenarioPlanDoc> {
    const filter: QueryFilter<ScenarioPlanDoc> = {}

    if (dto?.task_id) filter.task_id = dto.task_id
    if (dto?.generation_task_run_id) filter.generation_task_run_id = dto.generation_task_run_id
    if (dto?.status) filter.status = dto.status

    return filter
  }

  // ── CRUD ─────────────────────────────────────────────────────────────────

  async listPlans(dto?: ListScenarioPlanDto): Promise<OutScenarioPlanDto[]> {
    const params = { filter: this.buildFilter(dto) }
    return this.list(params)
  }

  async pagePlans(dto?: PageScenarioPlanDto): Promise<PageResult<OutScenarioPlanDto>> {
    const { page = 1, page_size = 10 } = dto || {}
    const filter = this.buildFilter(dto)
    return this.page({ ...filter, page, page_size })
  }

  async findScenarioPlanById(id: string | Types.ObjectId): Promise<OutScenarioPlanDto | null> {
    return this.findById(id)
  }

  async findOneByParams(dto: ListScenarioPlanDto): Promise<OutScenarioPlanDto | null> {
    return this.findOne(this.buildFilter(dto))
  }

  async createPlan(dto: CreateScenarioPlanDto): Promise<OutScenarioPlanDto> {
    return this.create(dto)
  }

  async updatePlan(id: string | Types.ObjectId, dto: UpdateScenarioPlanDto): Promise<OutScenarioPlanDto | null> {
    return this.updateById(id, dto)
  }

  async deletePlan(id: string | Types.ObjectId): Promise<boolean> {
    return this.deleteById(id)
  }
}

export const scenarioPlanRepository = new ScenarioPlanRepository()
