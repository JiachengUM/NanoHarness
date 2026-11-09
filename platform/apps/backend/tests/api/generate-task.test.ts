import { describe, it, expect, vi, beforeAll, afterAll, afterEach } from 'vitest'
import type { FastifyInstance } from 'fastify'
import { buildApp } from '../../src/core/app'
import { API_PREFIX } from '../../src/constants'

const mocks = vi.hoisted(() => ({
  listGenerationTasks: vi.fn(),
  pageGenerationTasks: vi.fn(),
  findById: vi.fn(),
  createGenerationTask: vi.fn(),
  updateGenerationTask: vi.fn(),
  deleteGenerationTask: vi.fn(),
}))

vi.mock('@eval-platform/database', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@eval-platform/database')>()
  return {
    ...actual,
    generationTaskRepository: mocks,
  }
})

const mockGenerationTask = {
  id: '507f1f77bcf86cd799439011',
  name: 'Test Generation Task',
  description: 'A test generation task',
  creator: 'system',
  created_time: '2024-01-01T00:00:00.000Z',
  updated_time: '2024-01-01T00:00:00.000Z',
}

describe('Generation Task Routes', () => {
  let app: FastifyInstance

  beforeAll(async () => {
    app = await buildApp({ logger: false })
  })

  afterAll(async () => {
    await app.close()
  })

  afterEach(() => {
    vi.resetAllMocks()
  })

  describe('GET /generation-task/list', () => {
    it('should return list of generation tasks', async () => {
      mocks.listGenerationTasks.mockResolvedValue([mockGenerationTask])

      const res = await app.inject({ method: 'GET', url: `${API_PREFIX}/generation-task/list` })

      expect(res.statusCode).toBe(200)
      const body = res.json()
      expect(body.code).toBe(200)
      expect(body.data).toHaveLength(1)
      expect(body.data[0].name).toBe('Test Generation Task')
    })

    it('should return empty list', async () => {
      mocks.listGenerationTasks.mockResolvedValue([])

      const res = await app.inject({ method: 'GET', url: `${API_PREFIX}/generation-task/list` })

      expect(res.statusCode).toBe(200)
      const body = res.json()
      expect(body.data).toHaveLength(0)
    })

    it('should pass name query parameter to repository', async () => {
      mocks.listGenerationTasks.mockResolvedValue([])

      await app.inject({ method: 'GET', url: `${API_PREFIX}/generation-task/list?name=foo` })

      expect(mocks.listGenerationTasks).toHaveBeenCalledWith({ name: 'foo' })
    })
  })

  describe('GET /generation-task/page', () => {
    const mockPageResult = {
      items: [mockGenerationTask],
      total: 1,
      page: 1,
      page_size: 10,
      pages: 1,
    }

    it('should return paginated results with defaults', async () => {
      mocks.pageGenerationTasks.mockResolvedValue(mockPageResult)

      const res = await app.inject({ method: 'GET', url: `${API_PREFIX}/generation-task/page` })

      expect(res.statusCode).toBe(200)
      const body = res.json()
      expect(body.data.total).toBe(1)
      expect(body.data.items).toHaveLength(1)
      expect(body.data.page).toBe(1)
      expect(body.data.page_size).toBe(10)
    })

    it('should pass pagination and filter params to repository', async () => {
      mocks.pageGenerationTasks.mockResolvedValue({ items: [], total: 0, page: 2, page_size: 5, pages: 0 })

      await app.inject({
        method: 'GET',
        url: `${API_PREFIX}/generation-task/page?page=2&page_size=5&name=bar`,
      })

      expect(mocks.pageGenerationTasks).toHaveBeenCalledWith({ page: 2, page_size: 5, name: 'bar' })
    })
  })

  describe('GET /generation-task/:id', () => {
    it('should return a generation task by id', async () => {
      mocks.findById.mockResolvedValue(mockGenerationTask)

      const res = await app.inject({
        method: 'GET',
        url: `${API_PREFIX}/generation-task/507f1f77bcf86cd799439011`,
      })

      expect(res.statusCode).toBe(200)
      const body = res.json()
      expect(body.code).toBe(200)
      expect(body.data.name).toBe('Test Generation Task')
      expect(mocks.findById).toHaveBeenCalledWith('507f1f77bcf86cd799439011')
    })

    it('should return 404 when generation task not found', async () => {
      mocks.findById.mockResolvedValue(null)

      const res = await app.inject({ method: 'GET', url: `${API_PREFIX}/generation-task/nonexistent` })

      expect(res.statusCode).toBe(404)
      const body = res.json()
      expect(body.code).toBe(404)
      expect(body.data).toBeNull()
      expect(body.message).toContain('not found')
    })
  })

  describe('POST /generation-task', () => {
    it('should create a generation task and return 201', async () => {
      mocks.createGenerationTask.mockResolvedValue(mockGenerationTask)

      const res = await app.inject({
        method: 'POST',
        url: `${API_PREFIX}/generation-task`,
        payload: { name: 'Test Generation Task', description: 'A test generation task' },
      })

      expect(res.statusCode).toBe(201)
      const body = res.json()
      expect(body.code).toBe(201)
      expect(body.data.name).toBe('Test Generation Task')
      expect(mocks.createGenerationTask).toHaveBeenCalledWith({
        name: 'Test Generation Task',
        description: 'A test generation task',
        creator: 'system',
      })
    })

    it('should create a generation task without description', async () => {
      mocks.createGenerationTask.mockResolvedValue({ ...mockGenerationTask, description: undefined })

      const res = await app.inject({
        method: 'POST',
        url: `${API_PREFIX}/generation-task`,
        payload: { name: 'Test Generation Task' },
      })

      expect(res.statusCode).toBe(201)
      expect(mocks.createGenerationTask).toHaveBeenCalledWith({
        name: 'Test Generation Task',
        creator: 'system',
      })
    })

    it('should return 400 when name is missing', async () => {
      const res = await app.inject({
        method: 'POST',
        url: `${API_PREFIX}/generation-task`,
        payload: { description: 'No name' },
      })

      expect(res.statusCode).toBe(400)
    })

    it('should return 400 when name is empty string', async () => {
      const res = await app.inject({
        method: 'POST',
        url: `${API_PREFIX}/generation-task`,
        payload: { name: '' },
      })

      expect(res.statusCode).toBe(400)
    })

    it('should return 400 when body is empty', async () => {
      const res = await app.inject({
        method: 'POST',
        url: `${API_PREFIX}/generation-task`,
        payload: {},
      })

      expect(res.statusCode).toBe(400)
    })
  })

  describe('PUT /generation-task/:id', () => {
    it('should update a generation task and return 200', async () => {
      mocks.updateGenerationTask.mockResolvedValue({ ...mockGenerationTask, name: 'Updated' })

      const res = await app.inject({
        method: 'PUT',
        url: `${API_PREFIX}/generation-task/507f1f77bcf86cd799439011`,
        payload: { name: 'Updated' },
      })

      expect(res.statusCode).toBe(200)
      const body = res.json()
      expect(body.data.name).toBe('Updated')
      expect(mocks.updateGenerationTask).toHaveBeenCalledWith('507f1f77bcf86cd799439011', {
        name: 'Updated',
        creator: 'system',
      })
    })

    it('should update description only', async () => {
      mocks.updateGenerationTask.mockResolvedValue({ ...mockGenerationTask, description: 'New desc' })

      const res = await app.inject({
        method: 'PUT',
        url: `${API_PREFIX}/generation-task/507f1f77bcf86cd799439011`,
        payload: { description: 'New desc' },
      })

      expect(res.statusCode).toBe(200)
      expect(mocks.updateGenerationTask).toHaveBeenCalledWith('507f1f77bcf86cd799439011', {
        description: 'New desc',
        creator: 'system',
      })
    })

    it('should return 404 when generation task not found', async () => {
      mocks.updateGenerationTask.mockResolvedValue(null)

      const res = await app.inject({
        method: 'PUT',
        url: `${API_PREFIX}/generation-task/nonexistent`,
        payload: { name: 'Updated' },
      })

      expect(res.statusCode).toBe(404)
      const body = res.json()
      expect(body.code).toBe(404)
      expect(body.data).toBeNull()
    })
  })

  describe('DELETE /generation-task/:id', () => {
    it('should delete a generation task and return 200', async () => {
      mocks.deleteGenerationTask.mockResolvedValue(true)

      const res = await app.inject({
        method: 'DELETE',
        url: `${API_PREFIX}/generation-task/507f1f77bcf86cd799439011`,
      })

      expect(res.statusCode).toBe(200)
      const body = res.json()
      expect(body.data).toBe(true)
      expect(mocks.deleteGenerationTask).toHaveBeenCalledWith('507f1f77bcf86cd799439011')
    })

    it('should return 404 when generation task not found', async () => {
      mocks.deleteGenerationTask.mockResolvedValue(false)

      const res = await app.inject({ method: 'DELETE', url: `${API_PREFIX}/generation-task/nonexistent` })

      expect(res.statusCode).toBe(404)
      const body = res.json()
      expect(body.code).toBe(404)
      expect(body.data).toBeNull()
      expect(body.message).toContain('not found')
    })
  })
})
