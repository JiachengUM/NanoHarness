import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import { Types } from 'mongoose'
import { connect, disconnect, generationTaskRepository, generationTaskRunRepository } from '../src'

const MONGO_URI = 'mongodb://127.0.0.1:27017/eval_platform'

describe('Mongoose ObjectId auto-cast', () => {
  let taskId: string
  const tagTreeId = new Types.ObjectId().toHexString()

  beforeAll(async () => {
    await connect(MONGO_URI)

    const task = await generationTaskRepository.createGenerationTask({
      name: '__test_cast_task__',
      description: 'For testing ObjectId cast',
    })
    taskId = task.id
  })

  afterAll(async () => {
    await generationTaskRunRepository.deleteMany({ generation_task_id: taskId })
    await generationTaskRepository.deleteById(taskId)
    await disconnect()
  })

  it('should create with string ObjectId fields', async () => {
    const created = await generationTaskRunRepository.createGenerationTaskRun({
      generation_task_id: taskId,
      tag_tree_id: tagTreeId,
      query: 'test query',
    })

    expect(created).toBeDefined()
    expect(created.id).toBeDefined()
    expect(typeof created.id).toBe('string')

    expect(created.generation_task_id).toBeDefined()
    expect(typeof created.generation_task_id).toBe('string')
    console.log('generation_task_id is string:', typeof created.generation_task_id === 'string')
    console.log('generation_task_id value:', created.generation_task_id)
    expect(created.generation_task_id).toBe(taskId)

    expect(typeof created.tag_tree_id).toBe('string')
    expect(created.tag_tree_id).toBe(tagTreeId)
  })

  it('should update with string ObjectId fields', async () => {
    const run = await generationTaskRunRepository.createGenerationTaskRun({
      generation_task_id: taskId,
      tag_tree_id: tagTreeId,
      query: 'query before update',
    })

    const secondTask = await generationTaskRepository.createGenerationTask({
      name: '__test_cast_task_2__',
    })

    const updated = await generationTaskRunRepository.updateGenerationTaskRun(run.id, {
      generation_task_id: secondTask.id,
      query: 'query after update',
    })

    expect(updated).toBeDefined()
    expect(updated?.query).toBe('query after update')
    expect(typeof updated?.generation_task_id).toBe('string')
    expect(updated?.generation_task_id).toBe(secondTask.id)

    await generationTaskRepository.deleteGenerationTask(secondTask.id)
  })

  it('should query with string ObjectId filter', async () => {
    const runs = await generationTaskRunRepository.listGenerationTaskRuns({
      generation_task_id: taskId,
    })

    expect(Array.isArray(runs)).toBe(true)
    expect(runs.length).toBeGreaterThan(0)
    expect(runs[0].generation_task_id).toBe(taskId)
    expect(typeof runs[0].generation_task_id).toBe('string')
  })
})
