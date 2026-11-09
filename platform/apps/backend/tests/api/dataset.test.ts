import { describe, it, expect, vi, beforeAll, afterAll, afterEach } from 'vitest'
import type { FastifyInstance } from 'fastify'
import { buildApp } from '../../src/core/app'
import { API_PREFIX } from '../../src/constants'

const mocks = vi.hoisted(() => ({
  listDatasets: vi.fn(),
  pageDatasets: vi.fn(),
  findById: vi.fn(),
  createDataset: vi.fn(),
  updateDataset: vi.fn(),
  deleteDataset: vi.fn(),
}))

const datasetItemMocks = vi.hoisted(() => ({
  listDatasetItems: vi.fn(),
  pageDatasetItems: vi.fn(),
  findById: vi.fn(),
  createDatasetItem: vi.fn(),
  updateDatasetItem: vi.fn(),
  deleteDatasetItem: vi.fn(),
}))

vi.mock('@eval-platform/database', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@eval-platform/database')>()
  return {
    ...actual,
    datasetRepository: mocks,
    datasetItemRepository: datasetItemMocks,
  }
})

const mockDataset = {
  id: '507f1f77bcf86cd799439011',
  name: 'Test Dataset',
  description: 'A test dataset',
  item_count: 0,
  creator: 'system',
  created_time: '2024-01-01T00:00:00.000Z',
  updated_time: '2024-01-01T00:00:00.000Z',
}

describe('Dataset Routes', () => {
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

  describe('GET /complex_reasoning_dataset/list', () => {
    it('should return list of datasets', async () => {
      mocks.listDatasets.mockResolvedValue([mockDataset])

      const res = await app.inject({ method: 'GET', url: `${API_PREFIX}/complex_reasoning_dataset/list` })

      expect(res.statusCode).toBe(200)
      const body = res.json()
      expect(body.code).toBe(200)
      expect(body.data).toHaveLength(1)
      expect(body.data[0].name).toBe('Test Dataset')
    })

    it('should return empty list', async () => {
      mocks.listDatasets.mockResolvedValue([])

      const res = await app.inject({ method: 'GET', url: `${API_PREFIX}/complex_reasoning_dataset/list` })

      expect(res.statusCode).toBe(200)
      const body = res.json()
      expect(body.data).toHaveLength(0)
    })

    it('should pass name query parameter to repository', async () => {
      mocks.listDatasets.mockResolvedValue([])

      await app.inject({ method: 'GET', url: `${API_PREFIX}/complex_reasoning_dataset/list?name=foo` })

      expect(mocks.listDatasets).toHaveBeenCalledWith({ name: 'foo' })
    })
  })

  describe('GET /complex_reasoning_dataset/page', () => {
    const mockPageResult = {
      items: [mockDataset],
      total: 1,
      page: 1,
      page_size: 10,
      pages: 1,
    }

    it('should return paginated results with defaults', async () => {
      mocks.pageDatasets.mockResolvedValue(mockPageResult)

      const res = await app.inject({ method: 'GET', url: `${API_PREFIX}/complex_reasoning_dataset/page` })

      expect(res.statusCode).toBe(200)
      const body = res.json()
      expect(body.data.total).toBe(1)
      expect(body.data.items).toHaveLength(1)
      expect(body.data.page).toBe(1)
      expect(body.data.page_size).toBe(10)
    })

    it('should pass pagination and filter params to repository', async () => {
      mocks.pageDatasets.mockResolvedValue({ items: [], total: 0, page: 2, page_size: 5, pages: 0 })

      await app.inject({
        method: 'GET',
        url: `${API_PREFIX}/complex_reasoning_dataset/page?page=2&page_size=5&name=bar`,
      })

      expect(mocks.pageDatasets).toHaveBeenCalledWith({ page: 2, page_size: 5, name: 'bar' })
    })
  })

  describe('GET /complex_reasoning_dataset/:id', () => {
    it('should return a dataset by id', async () => {
      mocks.findById.mockResolvedValue(mockDataset)

      const res = await app.inject({
        method: 'GET',
        url: `${API_PREFIX}/complex_reasoning_dataset/507f1f77bcf86cd799439011`,
      })

      expect(res.statusCode).toBe(200)
      const body = res.json()
      expect(body.code).toBe(200)
      expect(body.data.name).toBe('Test Dataset')
      expect(mocks.findById).toHaveBeenCalledWith('507f1f77bcf86cd799439011')
    })

    it('should return 404 when dataset not found', async () => {
      mocks.findById.mockResolvedValue(null)

      const res = await app.inject({ method: 'GET', url: `${API_PREFIX}/complex_reasoning_dataset/nonexistent` })

      expect(res.statusCode).toBe(404)
      const body = res.json()
      expect(body.code).toBe(404)
      expect(body.data).toBeNull()
      expect(body.message).toContain('not found')
    })
  })

  describe('POST /complex_reasoning_dataset', () => {
    it('should create a dataset and return 201', async () => {
      mocks.createDataset.mockResolvedValue(mockDataset)

      const res = await app.inject({
        method: 'POST',
        url: `${API_PREFIX}/complex_reasoning_dataset`,
        payload: { name: 'Test Dataset', description: 'A test dataset' },
      })

      expect(res.statusCode).toBe(201)
      const body = res.json()
      expect(body.code).toBe(201)
      expect(body.data.name).toBe('Test Dataset')
      expect(mocks.createDataset).toHaveBeenCalledWith({
        name: 'Test Dataset',
        description: 'A test dataset',
        creator: 'system',
      })
    })

    it('should create a dataset without description', async () => {
      mocks.createDataset.mockResolvedValue({ ...mockDataset, description: undefined })

      const res = await app.inject({
        method: 'POST',
        url: `${API_PREFIX}/complex_reasoning_dataset`,
        payload: { name: 'Test Dataset' },
      })

      expect(res.statusCode).toBe(201)
      expect(mocks.createDataset).toHaveBeenCalledWith({
        name: 'Test Dataset',
        creator: 'system',
      })
    })

    it('should return 400 when name is missing', async () => {
      const res = await app.inject({
        method: 'POST',
        url: `${API_PREFIX}/complex_reasoning_dataset`,
        payload: { description: 'No name' },
      })

      expect(res.statusCode).toBe(400)
    })

    it('should return 400 when name is empty string', async () => {
      const res = await app.inject({
        method: 'POST',
        url: `${API_PREFIX}/complex_reasoning_dataset`,
        payload: { name: '' },
      })

      expect(res.statusCode).toBe(400)
    })

    it('should return 400 when body is empty', async () => {
      const res = await app.inject({
        method: 'POST',
        url: `${API_PREFIX}/complex_reasoning_dataset`,
        payload: {},
      })

      expect(res.statusCode).toBe(400)
    })
  })

  describe('PUT /complex_reasoning_dataset/:id', () => {
    it('should update a dataset and return 200', async () => {
      mocks.updateDataset.mockResolvedValue({ ...mockDataset, name: 'Updated' })

      const res = await app.inject({
        method: 'PUT',
        url: `${API_PREFIX}/complex_reasoning_dataset/507f1f77bcf86cd799439011`,
        payload: { name: 'Updated' },
      })

      expect(res.statusCode).toBe(200)
      const body = res.json()
      expect(body.data.name).toBe('Updated')
      expect(mocks.updateDataset).toHaveBeenCalledWith('507f1f77bcf86cd799439011', {
        name: 'Updated',
        creator: 'system',
      })
    })

    it('should update description only', async () => {
      mocks.updateDataset.mockResolvedValue({ ...mockDataset, description: 'New desc' })

      const res = await app.inject({
        method: 'PUT',
        url: `${API_PREFIX}/complex_reasoning_dataset/507f1f77bcf86cd799439011`,
        payload: { description: 'New desc' },
      })

      expect(res.statusCode).toBe(200)
      expect(mocks.updateDataset).toHaveBeenCalledWith('507f1f77bcf86cd799439011', {
        description: 'New desc',
        creator: 'system',
      })
    })

    it('should return 404 when dataset not found', async () => {
      mocks.updateDataset.mockResolvedValue(null)

      const res = await app.inject({
        method: 'PUT',
        url: `${API_PREFIX}/complex_reasoning_dataset/nonexistent`,
        payload: { name: 'Updated' },
      })

      expect(res.statusCode).toBe(404)
      const body = res.json()
      expect(body.code).toBe(404)
      expect(body.data).toBeNull()
    })
  })

  describe('DELETE /complex_reasoning_dataset/:id', () => {
    it('should delete a dataset and return 200', async () => {
      mocks.deleteDataset.mockResolvedValue(true)

      const res = await app.inject({
        method: 'DELETE',
        url: `${API_PREFIX}/complex_reasoning_dataset/507f1f77bcf86cd799439011`,
      })

      expect(res.statusCode).toBe(200)
      const body = res.json()
      expect(body.data).toBe(true)
      expect(mocks.deleteDataset).toHaveBeenCalledWith('507f1f77bcf86cd799439011')
    })

    it('should return 404 when dataset not found', async () => {
      mocks.deleteDataset.mockResolvedValue(false)

      const res = await app.inject({ method: 'DELETE', url: `${API_PREFIX}/complex_reasoning_dataset/nonexistent` })

      expect(res.statusCode).toBe(404)
      const body = res.json()
      expect(body.code).toBe(404)
      expect(body.data).toBeNull()
      expect(body.message).toContain('not found')
    })
  })
})
