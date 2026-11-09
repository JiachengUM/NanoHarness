import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import { connect, disconnect, datasetRepository } from '../src'

const MONGO_URI = 'mongodb://127.0.0.1:27017/eval_platform'
const TEST_DATASET_NAME = '__test_dataset_crud__'

describe('Dataset CRUD', () => {
  beforeAll(async () => {
    await connect(MONGO_URI)
  })

  afterAll(async () => {
    await disconnect()
  })

  it('should create a dataset', async () => {
    await datasetRepository.deleteMany({ name: TEST_DATASET_NAME })

    const created = await datasetRepository.createDataset({
      name: TEST_DATASET_NAME,
      description: 'A sample dataset for CRUD test',
    })

    expect(created).toBeDefined()
    expect(created.id).toBeDefined()
    expect(created.name).toBe(TEST_DATASET_NAME)
    expect(created.description).toBe('A sample dataset for CRUD test')
  })

  it('should read a dataset by id', async () => {
    const datasets = await datasetRepository.listDatasets({ name: TEST_DATASET_NAME })
    expect(datasets.length).toBeGreaterThan(0)

    const found = await datasetRepository.findById(datasets[0].id)

    expect(found).toBeDefined()
    expect(found?.name).toBe(TEST_DATASET_NAME)
  })

  it('should update a dataset', async () => {
    const datasets = await datasetRepository.listDatasets({ name: TEST_DATASET_NAME })
    expect(datasets.length).toBeGreaterThan(0)

    const updated = await datasetRepository.updateDataset(datasets[0].id, {
      description: 'Description updated by test',
    })

    expect(updated).toBeDefined()
    expect(updated?.description).toBe('Description updated by test')
  })

  it('should list datasets', async () => {
    const datasets = await datasetRepository.listDatasets({})

    expect(datasets).toBeDefined()
    expect(Array.isArray(datasets)).toBe(true)
    expect(datasets.length).toBeGreaterThan(0)
  })

  it('should page datasets', async () => {
    const page = await datasetRepository.pageDatasets({ page: 1, page_size: 10 })

    expect(page).toBeDefined()
    expect(page.total).toBeGreaterThanOrEqual(0)
    expect(page.page).toBe(1)
    expect(page.page_size).toBe(10)
    expect(Array.isArray(page.items)).toBe(true)
  })

  it('should delete a dataset', async () => {
    const datasets = await datasetRepository.listDatasets({ name: TEST_DATASET_NAME })
    expect(datasets.length).toBeGreaterThan(0)

    const deleted = await datasetRepository.deleteDataset(datasets[0].id)
    expect(deleted).toBe(true)

    const afterDelete = await datasetRepository.findById(datasets[0].id)
    expect(afterDelete).toBeNull()
  })
})
