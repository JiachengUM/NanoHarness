import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import { connect, disconnect, generationTaskRepository } from '../src'

const MONGO_URI = 'mongodb://127.0.0.1:27017/eval_platform'
const TEST_TASK_NAME = '__test_generation_task_crud__'

describe('GenerationTask CRUD', () => {
  beforeAll(async () => {
    await connect(MONGO_URI)
  })

  afterAll(async () => {
    await disconnect()
  })

  it('should create a generation task', async () => {
    await generationTaskRepository.deleteMany({ name: TEST_TASK_NAME })

    const created = await generationTaskRepository.createGenerationTask({
      name: TEST_TASK_NAME,
      description: 'A sample generation task for CRUD test',
    })

    expect(created).toBeDefined()
    expect(created.id).toBeDefined()
    expect(created.name).toBe(TEST_TASK_NAME)
    expect(created.description).toBe('A sample generation task for CRUD test')
  })

  it('should read a generation task by id', async () => {
    const tasks = await generationTaskRepository.listGenerationTasks({ name: TEST_TASK_NAME })
    expect(tasks.length).toBeGreaterThan(0)

    const found = await generationTaskRepository.findById(tasks[0].id)

    expect(found).toBeDefined()
    expect(found?.name).toBe(TEST_TASK_NAME)
  })

  it('should update a generation task', async () => {
    const tasks = await generationTaskRepository.listGenerationTasks({ name: TEST_TASK_NAME })
    expect(tasks.length).toBeGreaterThan(0)

    const updated = await generationTaskRepository.updateGenerationTask(tasks[0].id, {
      description: 'Description updated by test',
    })

    expect(updated).toBeDefined()
    expect(updated?.description).toBe('Description updated by test')
  })

  it('should list generation tasks', async () => {
    const tasks = await generationTaskRepository.listGenerationTasks({})

    expect(tasks).toBeDefined()
    expect(Array.isArray(tasks)).toBe(true)
    expect(tasks.length).toBeGreaterThan(0)
  })

  it('should page generation tasks', async () => {
    const page = await generationTaskRepository.pageGenerationTasks({ page: 1, page_size: 10 })

    expect(page).toBeDefined()
    expect(page.total).toBeGreaterThanOrEqual(0)
    expect(page.page).toBe(1)
    expect(page.page_size).toBe(10)
    expect(Array.isArray(page.items)).toBe(true)
  })

  it('should delete a generation task', async () => {
    const tasks = await generationTaskRepository.listGenerationTasks({ name: TEST_TASK_NAME })
    expect(tasks.length).toBeGreaterThan(0)

    const deleted = await generationTaskRepository.deleteGenerationTask(tasks[0].id)
    expect(deleted).toBe(true)

    const afterDelete = await generationTaskRepository.findById(tasks[0].id)
    expect(afterDelete).toBeNull()
  })
})