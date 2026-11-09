import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import { connect, disconnect, datasetRepository, datasetItemRepository } from '../src'
import { DEFAULT_MAX_ROUND } from '../src/models/dataset-item/dataset-item.dto'

const MONGO_URI = 'mongodb://127.0.0.1:27017/eval_platform'
const TEST_DATASET_NAME = '__test_dataset_for_items__'

const SESSION_LEGACY = [{ role: 'user', content: '帮我导航去最近的加油站' }]

const SESSION_CONFIG = {
  user_query_list: [{ role: 'user', content: '现在几点了？' }],
  mock_info: { car_info: { speed: 60 } },
  mock_time: '2026-01-01 08:00:00',
}

function makeItemDto(datasetId: string, overrides: Record<string, unknown> = {}) {
  return {
    dataset_id: datasetId,
    case_id: `case_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    context_config: { env: 'test', location: '上海' },
    max_round: DEFAULT_MAX_ROUND,
    user_query_lists: [SESSION_LEGACY, SESSION_CONFIG],
    expected_script: '用户询问导航，助手给出正确路线',
    nl_assertion: ['助手应提供加油站位置', '回复中不应出现错误信息'],
    code_assertion: { car_state: 'navigating' },
    case_description: '测试导航场景',
    tags: ['navigation', 'smoke'],
    ...overrides,
  }
}

describe('DatasetItem CRUD', () => {
  let datasetId: string

  beforeAll(async () => {
    await connect(MONGO_URI)

    await datasetRepository.deleteMany({ name: TEST_DATASET_NAME })
    const dataset = await datasetRepository.createDataset({
      name: TEST_DATASET_NAME,
      description: 'Temporary dataset for item CRUD test',
    })
    datasetId = dataset.id
  })

  afterAll(async () => {
    await datasetRepository.deleteDataset(datasetId)
    await disconnect()
  })

  it('should create a dataset item with legacy and config sessions', async () => {
    const created = await datasetItemRepository.createDatasetItem(makeItemDto(datasetId))

    expect(created).toBeDefined()
    expect(created.id).toBeDefined()
    expect(created.case_id).toBeDefined()
    expect(created.max_round).toBe(DEFAULT_MAX_ROUND)
    expect(created.user_query_lists.length).toBe(2)
    expect(created.tags).toContain('navigation')
    expect(created.tags).toContain('smoke')
  })

  it('should read a dataset item by id', async () => {
    const created = await datasetItemRepository.createDatasetItem(makeItemDto(datasetId))
    const found = await datasetItemRepository.findById(created.id)

    expect(found).toBeDefined()
    expect(found?.case_id).toBe(created.case_id)
    expect(found?.context_config).toEqual({ env: 'test', location: '上海' })
    expect(found?.nl_assertion).toEqual(['助手应提供加油站位置', '回复中不应出现错误信息'])
    expect(found?.code_assertion).toEqual({ car_state: 'navigating' })
  })

  it('should update a dataset item', async () => {
    const created = await datasetItemRepository.createDatasetItem(makeItemDto(datasetId))
    const updated = await datasetItemRepository.updateDatasetItem(created.id, {
      case_description: '更新后的描述',
      tags: ['navigation', 'smoke', 'updated'],
      max_round: 5,
    })

    expect(updated).toBeDefined()
    expect(updated?.case_description).toBe('更新后的描述')
    expect(updated?.tags).toContain('updated')
    expect(updated?.max_round).toBe(5)
  })

  it('should create a dataset item with null assertions', async () => {
    const created = await datasetItemRepository.createDatasetItem(
      makeItemDto(datasetId, {
        case_id: `case_minimal_${Date.now()}`,
        nl_assertion: null,
        code_assertion: null,
        user_query_lists: [SESSION_CONFIG],
      }),
    )

    expect(created).toBeDefined()
    expect(created.nl_assertion).toBeNull()
    expect(created.code_assertion).toBeNull()
  })

  it('should list dataset items by dataset_id', async () => {
    const list = await datasetItemRepository.listDatasetItems({ dataset_id: datasetId })

    expect(list).toBeDefined()
    expect(Array.isArray(list)).toBe(true)
    expect(list.length).toBeGreaterThan(0)
  })

  it('should page dataset items', async () => {
    const page = await datasetItemRepository.pageDatasetItems({ dataset_id: datasetId, page: 1, page_size: 10 })

    expect(page).toBeDefined()
    expect(page.total).toBeGreaterThanOrEqual(0)
    expect(page.page).toBe(1)
    expect(page.page_size).toBe(10)
    expect(Array.isArray(page.items)).toBe(true)
  })

  it('should list dataset items by keyword', async () => {
    const created = await datasetItemRepository.createDatasetItem(makeItemDto(datasetId))
    const byCase = await datasetItemRepository.listDatasetItems({ dataset_id: datasetId, keyword: created.case_id })

    expect(byCase.length).toBe(1)
    expect(byCase[0].case_id).toBe(created.case_id)
  })

  it('should delete a single dataset item', async () => {
    const created = await datasetItemRepository.createDatasetItem(makeItemDto(datasetId))
    const deleted = await datasetItemRepository.deleteDatasetItem(created.id)

    expect(deleted).toBe(true)

    const afterDelete = await datasetItemRepository.findById(created.id)
    expect(afterDelete).toBeNull()
  })

  it('should bulk delete dataset items by dataset_id', async () => {
    await datasetItemRepository.createDatasetItem(makeItemDto(datasetId))
    await datasetItemRepository.createDatasetItem(makeItemDto(datasetId))

    const bulkDeleted = await datasetItemRepository.deleteByDatasetId(datasetId)
    expect(bulkDeleted).toBeGreaterThanOrEqual(2)

    const remaining = await datasetItemRepository.listDatasetItems({ dataset_id: datasetId })
    expect(remaining.length).toBe(0)
  })
})
