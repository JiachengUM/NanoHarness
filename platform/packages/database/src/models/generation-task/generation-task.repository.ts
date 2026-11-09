import type { QueryFilter } from 'mongoose'
import { Types } from 'mongoose'
import { BaseRepository, type ListParams, type PageResult } from '../../base/repository'
import { GenerationTask, GenerationTaskModel } from './generation-task.schema'
import type {
  CreateGenerationTaskDto,
  UpdateGenerationTaskDto,
  ListGenerationTaskDto,
  PageGenerationTaskDto,
  OutGenerationTaskDto,
} from './generation-task.dto'

export class GenerationTaskRepository extends BaseRepository<
  GenerationTask,
  OutGenerationTaskDto,
  CreateGenerationTaskDto,
  UpdateGenerationTaskDto
> {
  constructor() {
    super(GenerationTaskModel)
  }

  private buildFilter(dto?: ListGenerationTaskDto | PageGenerationTaskDto): QueryFilter<GenerationTask> {
    const filter: QueryFilter<GenerationTask> = {}

    if (dto?.name?.trim()) filter.name = { $regex: this.escapeRegex(dto.name.trim()), $options: 'i' }

    return filter
  }

  async createGenerationTask(dto: CreateGenerationTaskDto): Promise<OutGenerationTaskDto> {
    return this.create(dto)
  }

  async updateGenerationTask(
    id: string | Types.ObjectId,
    dto: UpdateGenerationTaskDto,
  ): Promise<OutGenerationTaskDto | null> {
    return this.updateById(id, dto)
  }

  async deleteGenerationTask(id: string | Types.ObjectId): Promise<boolean> {
    return this.deleteById(id)
  }

  async listGenerationTasks(dto?: ListGenerationTaskDto): Promise<OutGenerationTaskDto[]> {
    const params: ListParams<GenerationTask> = { filter: this.buildFilter(dto) }
    return this.list(params)
  }

  async pageGenerationTasks(dto?: PageGenerationTaskDto): Promise<PageResult<OutGenerationTaskDto>> {
    const { page = 1, page_size = 10 } = dto || {}
    const filter = this.buildFilter(dto)
    return this.page({ ...filter, page, page_size })
  }
}

export const generationTaskRepository = new GenerationTaskRepository()
