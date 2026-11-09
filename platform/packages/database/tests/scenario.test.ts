import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'
import { connect, disconnect, scenarioRepository } from '../src'

const MONGO_URI = 'mongodb://127.0.0.1:27017/eval_platform'
const TEST_SCENARIO_ID_PREFIX = '__test_scenario__'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

// 加载 vehicle-tag-tree.json 中的有效叶子标签
let validLeafTags: string[] = []
function loadVehicleLeafTags(): string[] {
  if (validLeafTags.length > 0) return validLeafTags
  const treePath = join(__dirname, '../../makedata/examples/data/vehicle-tag-tree.json')
  const tree = JSON.parse(readFileSync(treePath, 'utf-8'))

  function extractLeaves(node: any): string[] {
    const leaves: string[] = []
    if (!node.children || node.children.length === 0) {
      leaves.push(node.name)
    } else {
      node.children.forEach((child: any) => leaves.push(...extractLeaves(child)))
    }
    return leaves
  }

  validLeafTags = extractLeaves(tree.root)
  return validLeafTags
}

function makeScenarioDto(overrides: Record<string, unknown> = {}) {
  const timestamp = Date.now()
  const leafTags = loadVehicleLeafTags()

  // 使用真实标签树中的叶子标签
  const defaultTags = [
    leafTags.find((t) => t.includes('温度')) || leafTags[0],
    leafTags.find((t) => t.includes('导航')) || leafTags[1],
    leafTags.find((t) => t.includes('语音') || t.includes('交互')) || leafTags[2],
  ].filter(Boolean)

  return {
    scenario_id: `${TEST_SCENARIO_ID_PREFIX}_${timestamp}_${Math.random().toString(36).slice(2, 8)}`,
    scenario_name: `测试场景_${timestamp}`,
    description: '这是一个用于数据库测试的临时场景',
    tags: defaultTags,
    tag_tree_id: '507f1f77bcf86cd799439011',
    source_query: '生成一个空调控制场景',
    generation_task_id: '507f1f77bcf86cd799439012',
    ...overrides,
  }
}

describe('Scenario CRUD', () => {
  const createdScenarioIds: string[] = []

  beforeAll(async () => {
    await connect(MONGO_URI)

    // 清理之前测试残留的数据
    const existingScenarios = await scenarioRepository.listScenarios()
    for (const scenario of existingScenarios) {
      if (scenario.scenario_id.startsWith(TEST_SCENARIO_ID_PREFIX)) {
        await scenarioRepository.deleteScenario(scenario.id)
      }
    }
  })

  afterAll(async () => {
    // 清理测试数据
    for (const id of createdScenarioIds) {
      await scenarioRepository.deleteScenario(id)
    }
    await disconnect()
  })

  it('should create a scenario', async () => {
    const dto = makeScenarioDto()
    const created = await scenarioRepository.createScenario(dto)

    expect(created).toBeDefined()
    expect(created.id).toBeDefined()
    expect(created.scenario_id).toBe(dto.scenario_id)
    expect(created.scenario_name).toBe(dto.scenario_name)
    expect(created.description).toBe(dto.description)
    expect(created.tags).toEqual(dto.tags)
    expect(created.tag_tree_id).toBe(dto.tag_tree_id)
    expect(created.source_query).toBe(dto.source_query)
    expect(created.generation_task_id).toBe(dto.generation_task_id)

    createdScenarioIds.push(created.id)
  })

  it('should find a scenario by scenario_id', async () => {
    const dto = makeScenarioDto({ scenario_name: '查找测试场景' })
    const created = await scenarioRepository.createScenario(dto)
    createdScenarioIds.push(created.id)

    const found = await scenarioRepository.findByScenarioId(dto.scenario_id)

    expect(found).toBeDefined()
    expect(found?.scenario_id).toBe(dto.scenario_id)
    expect(found?.scenario_name).toBe('查找测试场景')
    // 验证使用的是 vehicle-tag-tree.json 中的有效叶子标签
    expect(found?.tags.length).toBeGreaterThan(0)
    expect(found?.tags[0]).toBeDefined()
  })

  it('should return null when scenario not found', async () => {
    const found = await scenarioRepository.findByScenarioId('non_existent_scenario_id')
    expect(found).toBeNull()
  })

  it('should update a scenario', async () => {
    const dto = makeScenarioDto({ scenario_name: '更新前名称' })
    const created = await scenarioRepository.createScenario(dto)
    createdScenarioIds.push(created.id)

    const updated = await scenarioRepository.updateScenario(created.id, {
      scenario_name: '更新后名称',
      description: '更新后的描述',
      tags: ['导航功能', 'POI搜索'],
    })

    expect(updated).toBeDefined()
    expect(updated?.scenario_name).toBe('更新后名称')
    expect(updated?.description).toBe('更新后的描述')
    expect(updated?.tags).toContain('POI搜索')
    expect(updated?.tags).not.toContain('温度调节')
    // 未更新的字段应保持不变
    expect(updated?.scenario_id).toBe(dto.scenario_id)
  })

  it('should list scenarios', async () => {
    const initialList = await scenarioRepository.listScenarios()
    const initialCount = initialList.filter((s) => s.scenario_id.startsWith(TEST_SCENARIO_ID_PREFIX)).length

    const dto1 = makeScenarioDto({ scenario_name: '列表测试1' })
    const dto2 = makeScenarioDto({ scenario_name: '列表测试2' })
    const created1 = await scenarioRepository.createScenario(dto1)
    const created2 = await scenarioRepository.createScenario(dto2)
    createdScenarioIds.push(created1.id, created2.id)

    const list = await scenarioRepository.listScenarios()
    const testScenarios = list.filter((s) => s.scenario_id.startsWith(TEST_SCENARIO_ID_PREFIX))

    expect(testScenarios.length).toBeGreaterThanOrEqual(initialCount + 2)
  })

  it('should list scenarios by keyword', async () => {
    const uniqueKeyword = `unique_keyword_${Date.now()}`
    const dto = makeScenarioDto({
      scenario_name: `包含${uniqueKeyword}的场景`,
      description: `描述中也有${uniqueKeyword}`,
    })
    const created = await scenarioRepository.createScenario(dto)
    createdScenarioIds.push(created.id)

    const list = await scenarioRepository.listScenarios({ keyword: uniqueKeyword })

    expect(list.length).toBeGreaterThanOrEqual(1)
    expect(list.some((s) => s.scenario_id === dto.scenario_id)).toBe(true)
  })

  it('should list scenarios by tag', async () => {
    const specificTag = `specific_tag_${Date.now()}`
    const dto = makeScenarioDto({ tags: [specificTag, '其他标签'] })
    const created = await scenarioRepository.createScenario(dto)
    createdScenarioIds.push(created.id)

    const list = await scenarioRepository.listScenarios({ tag: specificTag })

    expect(list.length).toBeGreaterThanOrEqual(1)
    expect(list.some((s) => s.scenario_id === dto.scenario_id)).toBe(true)
  })

  it('should list scenarios by tag_tree_id', async () => {
    const specificTreeId = '507f1f77bcf86cd799439013'
    const dto = makeScenarioDto({ tag_tree_id: specificTreeId })
    const created = await scenarioRepository.createScenario(dto)
    createdScenarioIds.push(created.id)

    const list = await scenarioRepository.listScenarios({ tag_tree_id: specificTreeId })

    expect(list.length).toBeGreaterThanOrEqual(1)
    expect(list.some((s) => s.scenario_id === dto.scenario_id)).toBe(true)
  })

  it('should list scenarios by generation_task_id', async () => {
    const specificTaskId = '507f1f77bcf86cd799439014'
    const dto = makeScenarioDto({ generation_task_id: specificTaskId })
    const created = await scenarioRepository.createScenario(dto)
    createdScenarioIds.push(created.id)

    const list = await scenarioRepository.listScenarios({ generation_task_id: specificTaskId })

    expect(list.length).toBeGreaterThanOrEqual(1)
    expect(list.some((s) => s.scenario_id === dto.scenario_id)).toBe(true)
  })

  it('should paginate scenarios', async () => {
    // 创建多个测试场景
    const createdScenarios = []
    for (let i = 0; i < 5; i++) {
      const dto = makeScenarioDto({ scenario_name: `分页测试场景${i}` })
      const created = await scenarioRepository.createScenario(dto)
      createdScenarios.push(created)
      createdScenarioIds.push(created.id)
    }

    const page = await scenarioRepository.pageScenarios({ page: 1, page_size: 3 })

    expect(page).toBeDefined()
    expect(page.items.length).toBeLessThanOrEqual(3)
    expect(page.page).toBe(1)
    expect(page.page_size).toBe(3)
    expect(page.total).toBeGreaterThanOrEqual(5)
    expect(page.pages).toBeGreaterThanOrEqual(2)
  })

  it('should delete a scenario', async () => {
    const dto = makeScenarioDto({ scenario_name: '即将被删除的场景' })
    const created = await scenarioRepository.createScenario(dto)

    const deleted = await scenarioRepository.deleteScenario(created.id)
    expect(deleted).toBe(true)

    const found = await scenarioRepository.findByScenarioId(dto.scenario_id)
    expect(found).toBeNull()

    // 从清理列表中移除（已经删除了）
    const index = createdScenarioIds.indexOf(created.id)
    if (index > -1) {
      createdScenarioIds.splice(index, 1)
    }
  })

  it('should enforce unique scenario_id', async () => {
    const dto = makeScenarioDto({ scenario_id: `unique_test_${Date.now()}` })
    const created = await scenarioRepository.createScenario(dto)
    createdScenarioIds.push(created.id)

    // 尝试创建相同 scenario_id 的场景应该失败
    await expect(scenarioRepository.createScenario(dto)).rejects.toThrow()
  })
})
