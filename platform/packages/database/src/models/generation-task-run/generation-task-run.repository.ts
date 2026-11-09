import type { QueryFilter, HydratedDocument } from 'mongoose'
import { Types } from 'mongoose'
import { BaseRepository, type ListParams, type PageResult } from '../../base/repository'
import { GenerationTaskRun, GenerationTaskRunModel } from './generation-task-run.schema'
import type {
  CreateGenerationTaskRunDto,
  UpdateGenerationTaskRunDto,
  ListGenerationTaskRunDto,
  PageGenerationTaskRunDto,
  OutGenerationTaskRunDto,
} from './generation-task-run.dto'
import { scenarioPlanRepository } from '../scenario-plan'
import { scenarioRepository } from '../scenario'

export class GenerationTaskRunRepository extends BaseRepository<
  GenerationTaskRun,
  OutGenerationTaskRunDto,
  CreateGenerationTaskRunDto,
  UpdateGenerationTaskRunDto
> {
  constructor() {
    super(GenerationTaskRunModel)
  }

  protected toDto(doc: HydratedDocument<GenerationTaskRun>): OutGenerationTaskRunDto {
    return {
      ...doc.toObject(),
      generation_task_id: doc.generation_task_id.toString(),
      tag_tree_id: doc.tag_tree_id.toString(),
    } as OutGenerationTaskRunDto
  }

  private buildFilter(dto?: ListGenerationTaskRunDto | PageGenerationTaskRunDto): QueryFilter<GenerationTaskRun> {
    const filter: QueryFilter<GenerationTaskRun> = {}

    if (dto?.generation_task_id?.trim()) filter.generation_task_id = dto.generation_task_id.trim()
    if (dto?.status?.trim()) filter.status = dto.status.trim()

    return filter
  }

  async createGenerationTaskRun(dto: CreateGenerationTaskRunDto): Promise<OutGenerationTaskRunDto> {
    return this.create(dto)
  }

  async updateGenerationTaskRun(
    id: string | Types.ObjectId,
    dto: UpdateGenerationTaskRunDto,
  ): Promise<OutGenerationTaskRunDto | null> {
    return this.updateById(id, dto)
  }

  async deleteGenerationTaskRun(id: string | Types.ObjectId): Promise<boolean> {
    return this.deleteById(id)
  }

  async listGenerationTaskRuns(dto?: ListGenerationTaskRunDto): Promise<OutGenerationTaskRunDto[]> {
    const params: ListParams<GenerationTaskRun> = { filter: this.buildFilter(dto) }
    return this.list(params)
  }

  async pageGenerationTaskRuns(dto?: PageGenerationTaskRunDto): Promise<PageResult<OutGenerationTaskRunDto>> {
    const { page = 1, page_size = 10 } = dto || {}
    const filter = this.buildFilter(dto)
    return this.page({ ...filter, page, page_size })
  }

  async findGenerationTaskRunById(id: string | Types.ObjectId): Promise<OutGenerationTaskRunDto | null> {
    return this.findById(id)
  }

  async findGenerationTaskRunByScenarioPlanId(
    scenarioPlanId: string | Types.ObjectId,
  ): Promise<OutGenerationTaskRunDto | null> {
    const plan = await scenarioPlanRepository.findScenarioPlanById(scenarioPlanId)
    if (!plan?.generation_task_run_id) return null
    return this.findById(plan.generation_task_run_id)
  }

  async findGenerationTaskRunByScenarioId(
    scenarioId: string | Types.ObjectId,
  ): Promise<OutGenerationTaskRunDto | null> {
    const scenario = await scenarioRepository.findById(scenarioId)
    if (!scenario?.scenario_plan_id) return null
    return this.findGenerationTaskRunByScenarioPlanId(scenario.scenario_plan_id)
  }
}

export const generationTaskRunRepository = new GenerationTaskRunRepository()
