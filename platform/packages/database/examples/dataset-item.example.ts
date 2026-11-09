import { connect, disconnect, datasetRepository, datasetItemRepository } from '../src'
import { DEFAULT_MAX_ROUND } from '../src/models/dataset-item/dataset-item.dto'

const MONGO_URI = 'mongodb://127.0.0.1:27017/eval_platform'

// ── 测试数据工厂 ──────────────────────────────────────────────────────────

const TEST_DATASET_NAME = '__test_dataset_for_items__'

/** 旧格式 session：直接是 Message 数组 */
const SESSION_LEGACY = [{ role: 'user', content: '帮我导航去最近的加油站' }]

/** 新格式 session：DialogueRoundConfig */
const SESSION_CONFIG = {
  user_query_list: [{ role: 'user', content: '现在几点了？' }],
  mock_info: { car_info: { speed: 60 } },
  mock_time: '2026-01-01 08:00:00',
}

function makeItemDto(datasetId: string, overrides: Record<string, unknown> = {}) {
  return {
    dataset_id: datasetId,
    case_id: `case_${Date.now()}`,
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

// ── 主流程 ────────────────────────────────────────────────────────────────

async function run() {
  await connect(MONGO_URI)
  console.log('Connected to MongoDB:', MONGO_URI)

  // 准备：取或建一个测试用 dataset，确保 dataset_id 合法存在
  await datasetRepository.deleteMany({ name: TEST_DATASET_NAME })
  const dataset = await datasetRepository.createDataset({
    name: TEST_DATASET_NAME,
    description: 'Temporary dataset for item CRUD test',
  })
  const datasetId = dataset.id
  console.log('Prepared dataset:', datasetId)

  try {
    // ── 1. 创建（旧格式 + 新格式 session 均包含） ─────────────────────────
    const created = await datasetItemRepository.createDatasetItem(makeItemDto(datasetId))
    console.log('Create:', {
      id: created.id,
      case_id: created.case_id,
      max_round: created.max_round,
      sessions: created.user_query_lists.length,
      tags: created.tags,
    })

    // ── 2. 按 id 查询 ──────────────────────────────────────────────────────
    const found = await datasetItemRepository.findById(created.id)
    console.log('Read by id:', {
      case_id: found?.case_id,
      context_config: found?.context_config,
      nl_assertion: found?.nl_assertion,
      code_assertion: found?.code_assertion,
    })

    // ── 3. 更新 ───────────────────────────────────────────────────────────
    const updated = await datasetItemRepository.updateDatasetItem(created.id, {
      case_description: '更新后的描述',
      tags: ['navigation', 'smoke', 'updated'],
      max_round: 5,
    })
    console.log('Update:', {
      case_description: updated?.case_description,
      tags: updated?.tags,
      max_round: updated?.max_round,
    })

    // ── 4. 创建第二条（仅 nl_assertion=null、code_assertion=null） ─────────
    const created2 = await datasetItemRepository.createDatasetItem(
      makeItemDto(datasetId, {
        case_id: `case_minimal_${Date.now()}`,
        nl_assertion: null,
        code_assertion: null,
        user_query_lists: [SESSION_CONFIG],
      }),
    )
    console.log('Create minimal (null assertions):', {
      id: created2.id,
      nl_assertion: created2.nl_assertion,
      code_assertion: created2.code_assertion,
    })

    // ── 5. 列表（按 dataset_id 过滤） ──────────────────────────────────────
    const list = await datasetItemRepository.listDatasetItems({ dataset_id: datasetId })
    console.log('List count (by dataset_id):', list.length)

    // ── 6. 分页 ───────────────────────────────────────────────────────────
    const page = await datasetItemRepository.pageDatasetItems({ dataset_id: datasetId, page: 1, page_size: 10 })
    console.log('Page result:', {
      total: page.total,
      page: page.page,
      page_size: page.page_size,
      pages: page.pages,
      items: page.items.length,
    })

    // // ── 7. 删除单条 ───────────────────────────────────────────────────────
    // const deleted = await datasetItemRepository.deleteDatasetItem(created.id)
    // const afterDelete = await datasetItemRepository.findById(created.id)
    // console.log('Delete single:', deleted, '| Read after delete:', afterDelete)

    // // ── 8. 批量删除（按 dataset_id） ───────────────────────────────────────────
    // const bulkDeleted = await datasetItemRepository.deleteByDatasetId(datasetId)
    // const remaining = await datasetItemRepository.listDatasetItems({ dataset_id: datasetId })
    // console.log('Delete by dataset_id count:', bulkDeleted, '| Remaining:', remaining.length)
  } finally {
    // 清理测试用 dataset
    await datasetRepository.deleteDataset(datasetId)
    await disconnect()
    console.log('Disconnected from MongoDB')
  }
}

run().catch((error: unknown) => {
  console.error('dataset-item CRUD test failed:', error)
  process.exitCode = 1
})
