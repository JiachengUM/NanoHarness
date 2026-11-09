import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import type { FastifyInstance } from 'fastify'
import { buildApp } from '../../src/core/app'
import { API_PREFIX } from '../../src/constants'
import {
  connect,
  disconnect,
  datasetRepository,
  tagTreeRepository,
  scenarioRepository,
  datasetItemRepository,
  generationTaskRepository,
} from '@eval-platform/database'
import { readFileSync, existsSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const MONGO_URI = 'mongodb://127.0.0.1:27017/eval_platform_e2e_test'

/**
 * 解析 SSE (Server-Sent Events) 响应
 */
function parseSSE(body: string): Array<{ type: string; data: any }> {
  const events: Array<{ type: string; data: any }> = []
  const lines = body.split('\n')
  let currentData: string | null = null

  for (const line of lines) {
    if (line.startsWith('data: ')) {
      currentData = line.substring(6)
      try {
        const parsed = JSON.parse(currentData)
        events.push(parsed)
      } catch (e) {
        // 忽略解析失败的行
      }
    }
  }

  return events
}

/**
 * 加载测试用标签树。
 * 优先使用 makedata 包 examples/data 下的 vehicle-tag-tree.json（含例子描述的增强版），
 * 若不存在（该文件为本地生成产物，可能缺失），回退到仓库 canonical base 标签树。
 */
function loadVehicleTagTree(): any {
  const enrichedPath = join(
    __dirname,
    '../../../../packages/makedata/examples/data/vehicle-tag-tree.json',
  )
  if (existsSync(enrichedPath)) {
    return JSON.parse(readFileSync(enrichedPath, 'utf-8'))
  }

  const canonicalPath = join(
    __dirname,
    '../../../../../projects/mind/mem/auto_test_script/make_datasets_for_vehicle_assistant/artifacts/base/base_vehicle_assistant_case_tag_tree.json',
  )
  if (!existsSync(canonicalPath)) {
    throw new Error(
      `找不到标签树数据文件，已尝试:\n  ${enrichedPath}\n  ${canonicalPath}`,
    )
  }
  return JSON.parse(readFileSync(canonicalPath, 'utf-8'))
}

describe('End-to-End API Test', () => {
  let app: FastifyInstance
  let tagTreeName: string
  let tagTreeMongoId: string
  let scenarioIds: string[] = []
  let datasetId: string
  let generationTaskId: string

  beforeAll(async () => {
    // 连接数据库
    console.log('Connecting to MongoDB...')
    await connect(MONGO_URI)
    console.log('MongoDB connected')

    // 清理测试数据
    console.log('Cleaning up test data...')
    await cleanupTestData()
    console.log('Test data cleaned')

    // 构建应用
    console.log('Building app...')
    app = await buildApp({ logger: false })
    console.log('App built successfully')
  }, 60000) // 60秒超时，包含应用构建

  afterAll(async () => {
    // 关闭应用
    await app.close()

    // 清理测试数据（包括本次测试生成的所有数据）
    await cleanupTestData()

    // 断开数据库连接
    await disconnect()
  }, 30000)

  async function cleanupTestData() {
    console.log('Cleaning up test data...')

    // 1. 清理测试数据集及其用例（通过记录的 datasetId）
    if (datasetId) {
      try {
        // 先删除数据集中的所有用例
        await datasetItemRepository.deleteByDatasetId(datasetId)
        console.log(`Deleted cases for dataset: ${datasetId}`)
        // 再删除数据集
        await datasetRepository.deleteDataset(datasetId)
        console.log(`Deleted dataset: ${datasetId}`)
      } catch (error) {
        console.warn(`Failed to delete dataset ${datasetId}:`, error)
      }
    }

    // 2. 清理本次测试生成的场景（通过记录的 tagTreeMongoId）
    if (tagTreeMongoId) {
      try {
        // 查找该标签树下的所有场景
        const scenarios = await scenarioRepository.listScenarios({ tag_tree_id: tagTreeMongoId })
        for (const scenario of scenarios) {
          await scenarioRepository.deleteScenario(scenario.id)
          console.log(`Deleted scenario: ${scenario.scenario_id}`)
        }
        console.log(`Deleted ${scenarios.length} scenarios for tag tree: ${tagTreeName}`)
      } catch (error) {
        console.warn(`Failed to delete scenarios for tag tree ${tagTreeName}:`, error)
      }
    }

    // 3. 清理测试标签树
    if (tagTreeName) {
      try {
        const tree = await tagTreeRepository.findByName(tagTreeName)
        if (tree) {
          await tagTreeRepository.deleteTagTree(tree.id)
          console.log(`Deleted tag tree: ${tagTreeName}`)
        }
      } catch (error) {
        console.warn(`Failed to delete tag tree ${tagTreeName}:`, error)
      }
    }

    if (generationTaskId) {
      try {
        await generationTaskRepository.deleteGenerationTask(generationTaskId)
        console.log(`Deleted generation task: ${generationTaskId}`)
      } catch (error) {
        console.warn(`Failed to delete generation task ${generationTaskId}:`, error)
      }
    }

    // 4. 兜底清理：删除所有 e2e_test_ 前缀的数据（防止之前测试中断留下的数据）
    // 清理标签树
    const trees = await tagTreeRepository.listTagTrees()
    for (const tree of trees) {
      if (tree.name.startsWith('e2e_test_')) {
        await tagTreeRepository.deleteTagTree(tree.id)
        console.log(`Deleted legacy tag tree: ${tree.name}`)
      }
    }

    // 清理场景（只清理 e2e_test_ 前缀的，避免误删其他数据）
    const allScenarios = await scenarioRepository.listScenarios()
    for (const scenario of allScenarios) {
      if (scenario.scenario_id.startsWith('e2e_test_')) {
        await scenarioRepository.deleteScenario(scenario.id)
        console.log(`Deleted legacy scenario: ${scenario.scenario_id}`)
      }
    }

    // 清理数据集
    const datasets = await datasetRepository.listDatasets()
    for (const dataset of datasets) {
      if (dataset.name.startsWith('e2e_test_')) {
        await datasetItemRepository.deleteByDatasetId(dataset.id)
        await datasetRepository.deleteDataset(dataset.id)
        console.log(`Deleted legacy dataset: ${dataset.name}`)
      }
    }

    console.log('Test data cleanup completed')
  }

  it('1. 上传标签树', async () => {
    const tagTreeData = loadVehicleTagTree()
    tagTreeName = `e2e_test_vehicle_tree_${Date.now()}`

    console.log('Tag tree name:', tagTreeName)
    console.log('Tag tree data keys:', Object.keys(tagTreeData))

    const res = await app.inject({
      method: 'POST',
      url: `${API_PREFIX}/tag-tree/`,
      payload: {
        name: tagTreeName,
        description: '端到端测试用车载助手标签树',
        tree: tagTreeData,
      },
    })

    console.log('Response status:', res.statusCode)
    console.log('Response body:', res.body.substring(0, 300))

    // POST /tag-tree/ 使用 reply.success 包裹，statusCode=201
    expect(res.statusCode).toBe(201)
    const body = res.json()
    expect(body.code).toBe(201)
    expect(body.data).toBeDefined()
    expect(body.data.name).toBe(tagTreeName)
    tagTreeMongoId = body.data.id
    expect(tagTreeMongoId).toBeDefined()
  })

  it('2. 查看标签树列表', async () => {
    const res = await app.inject({
      method: 'GET',
      url: `${API_PREFIX}/tag-tree/list-brief`,
    })

    console.log('List tag trees response:', res.statusCode, res.body.substring(0, 200))

    expect(res.statusCode).toBe(200)
    const body = res.json()
    // reply.success 包裹：data 为数组
    expect(body.code).toBe(200)
    expect(Array.isArray(body.data)).toBe(true)

    // 验证我们上传的标签树在列表中
    const ourTree = body.data.find((t: any) => t.name === tagTreeName)
    expect(ourTree).toBeDefined()
    expect(ourTree.description).toBe('端到端测试用车载助手标签树')
  })

  it('3. 预览标签树', async () => {
    const res = await app.inject({
      method: 'GET',
      url: `${API_PREFIX}/tag-tree/${encodeURIComponent(tagTreeName)}/preview`,
    })

    console.log('Preview tag tree response:', res.statusCode, res.body.substring(0, 200))

    expect(res.statusCode).toBe(200)
    const body = res.json()
    // reply.success 包裹：data 为预览字符串
    expect(body.code).toBe(200)
    expect(typeof body.data).toBe('string')
    // 验证预览内容包含标签树关键信息
    expect(body.data).toContain('车机助手评测标签树')
    expect(body.data).toContain('温度增减调节')
    expect(body.data).toContain('叶子标签总数')
  })

  it('4. 创建场景生成计划 (Scenario Planning)', async () => {
    const query = '帮我生成先说过自己住在哪儿，然后在新的对话中导航回家的场景'
    const generationTask = await generationTaskRepository.createGenerationTask({
      name: `e2e_task_${Date.now()}`,
      description: 'E2E 场景生成任务',
      creator: 'test',
    })
    const taskId = generationTask.id
    generationTaskId = taskId

    console.log('\n========================================')
    console.log('  步骤 4.1: 创建场景生成计划')
    console.log('========================================')
    console.log(`  Query: ${query}`)
    console.log(`  Task ID: ${taskId}`)

    const res = await app.inject({
      method: 'POST',
      url: `${API_PREFIX}/scenario-planning/generate`,
      payload: {
        query: query,
        tag_tree_name: tagTreeName,
        task_id: taskId,
      },
    })

    console.log('Create plan response status:', res.statusCode)

    expect(res.statusCode).toBe(200)
    const body = res.json()
    const plan = body.data

    expect(plan.id).toBeDefined()
    expect(plan.task_description).toBeDefined()
    expect(plan.target_tags).toBeDefined()
    expect(plan.target_tags.length).toBeGreaterThan(0)
    // target_scenario_count 已从 Plan 剥离，改由 Pattern 阶段产出
    expect(plan.interpretation_notes).toBeDefined()

    // 保存 ScenarioPlan id 供后续测试使用
    const planId = plan.id
    console.log(`\n  Plan 创建成功:`)
    console.log(`    Plan ID: ${planId}`)
    console.log(`    目标标签数: ${plan.target_tags.length}`)

    // 将 planId 附加到 global 供后续测试使用
    ;(globalThis as any).e2eTestPlanId = planId
    ;(globalThis as any).e2eTestTaskId = taskId
  }, 120000)

  it('4.2 确认场景生成计划', async () => {
    const planId = (globalThis as any).e2eTestPlanId
    expect(planId).toBeDefined()

    console.log('\n========================================')
    console.log('  步骤 4.2: 确认 Plan')
    console.log('========================================')
    console.log(`  Plan ID: ${planId}`)

    // 先获取 Plan 详情查看
    const getRes = await app.inject({
      method: 'GET',
      url: `${API_PREFIX}/scenario-planning/${planId}`,
    })

    expect(getRes.statusCode).toBe(200)
    const planDetail = getRes.json().data
    expect(planDetail.status).toBe('pending')

    console.log(`  查看 Plan 详情:`)
    console.log(`    任务描述: ${planDetail.task_description.substring(0, 100)}...`)
    console.log(`    理解说明: ${planDetail.interpretation_notes.substring(0, 100)}...`)

    // 确认 Plan
    const confirmRes = await app.inject({
      method: 'PUT',
      url: `${API_PREFIX}/scenario-planning/${planId}`,
      payload: {
        status: 'confirmed',
      },
    })

    expect(confirmRes.statusCode).toBe(200)
    expect(confirmRes.json().data.status).toBe('confirmed')

    console.log('\n  ✅ Plan 已确认')
  })

  it(
    '4.3 使用 Plan 流式生成场景',
    async () => {
      const planId = (globalThis as any).e2eTestPlanId
      expect(planId).toBeDefined()

      console.log('\n========================================')
      console.log('  步骤 4.3: 使用 Plan 流式生成场景')
      console.log('========================================')
      console.log(`  Plan ID: ${planId}`)

      const streamStart = Date.now()

      const res = await app.inject({
        method: 'POST',
        url: `${API_PREFIX}/scenario-generation-stream`,
        payload: {
          scenarioPlanId: planId,
          saveToDb: true,
          // 限制阶段2迭代数以控制耗时；阶段1会遍历全部 pattern
          maxIterations: 3,
          initialBatchSize: 3,
          maxRefineRoundsPerBatch: 1,
        },
      })

      console.log('Generate scenarios stream response status:', res.statusCode)

      expect(res.statusCode).toBe(200)
      expect(res.headers['content-type']).toContain('text/event-stream')

      // 解析SSE响应
      const events = parseSSE(res.body)

      // 收集事件
      const planEvent = events.find((e) => e.type === 'plan')
      const patternsEvent = events.find((e) => e.type === 'patterns')
      const scenarios: any[] = []
      const progressEvents: any[] = []
      let completeEvent: any = null
      let errorEvent: any = null
      // 注意：app.inject 会缓冲整个 SSE 响应，直到流结束才返回 res.body。
      // 因此下面在解析阶段计算的 firstScenarioAt 实际等于「场景流总耗时」，
      // 并非真实的首个场景到达延迟。真实首场景延迟需用真正的流式客户端
      // （如前端 EventSource）测量，无法在本 inject 测试中得出。
      let firstScenarioAt: number | null = null

      for (const event of events) {
        if (event.type === 'plan') {
          console.log('\n  [Plan] 收到 Plan 信息:')
          console.log(`    目标标签数: ${event.data.target_tags?.length}`)
        } else if (event.type === 'patterns') {
          console.log(`  [Patterns] 生成 ${event.data.patterns?.length} 个模式，目标场景数: ${event.data.target_scenario_count}`)
        } else if (event.type === 'scenario') {
          if (firstScenarioAt === null) {
            firstScenarioAt = Date.now() - streamStart
            console.log(`\n  ⏱️  场景流式生成总耗时（inject 缓冲，非首场景延迟）: ${(firstScenarioAt / 1000).toFixed(1)}s`)
          }
          const sc = event.data.scenario
          scenarios.push(sc)
          console.log(
            `  [场景] ${sc?.scenario_name} (${event.data.totalScenarios}/${event.data.targetScenarioCount})`,
          )
        } else if (event.type === 'progress') {
          progressEvents.push(event.data)
          const icon = event.data.satisfied ? '✅' : event.data.progressPercentage >= 100 ? '⏳' : '🔄'
          console.log(
            `  [进度] ${event.data.stage} ${event.data.totalScenarios}/${event.data.targetScenarioCount} (${event.data.progressPercentage}%) ${icon}`,
          )
        } else if (event.type === 'complete') {
          completeEvent = event.data
          console.log(`\n  [完成] 生成结束:`)
          console.log(`    实际生成: ${completeEvent.actualCount}/${completeEvent.targetCount}`)
          console.log(`    达成率: ${completeEvent.achievementRate}%`)
          console.log(`    总迭代: ${completeEvent.totalIterations}`)
          console.log(`    覆盖率: ${completeEvent.finalCoveragePercentage}%`)
        } else if (event.type === 'error') {
          errorEvent = event.data
          console.error(`  [错误] ${event.data.message}`)
        }
      }

      // 验证
      expect(errorEvent).toBeNull()
      expect(planEvent).toBeDefined()
      expect(patternsEvent).toBeDefined()
      expect(scenarios.length).toBeGreaterThanOrEqual(1)
      expect(completeEvent).toBeDefined()
      expect(completeEvent.scenarioPlanId).toBe(planId)

      // 验证场景字段
      for (const scenario of scenarios) {
        expect(scenario.scenario_id).toBeDefined()
        expect(scenario.scenario_name).toBeDefined()
        expect(scenario.tags).toBeDefined()
        scenarioIds.push(scenario.scenario_id)
      }

      console.log(`\n  ✅ 场景生成完成: ${scenarios.length} 个场景，场景流总耗时 ${(firstScenarioAt! / 1000).toFixed(1)}s`)
      console.log(`Saved ${scenarioIds.length} scenario IDs for subsequent tests`)
    },
    600000,
  )

  it('5. 查看标签树下的场景列表', async () => {
    const res = await app.inject({
      method: 'GET',
      url: `${API_PREFIX}/scenario-management/by-tag-tree/${encodeURIComponent(tagTreeName)}`,
    })

    console.log('List scenarios by tag tree response:', res.statusCode, res.body.substring(0, 300))

    expect(res.statusCode).toBe(200)
    const body = res.json().data
    expect(Array.isArray(body)).toBe(true)

    console.log(`Found ${body.length} scenarios for tag tree ${tagTreeName}`)

    // 如果有场景生成，验证它们都在列表中
    if (scenarioIds.length > 0) {
      for (const scenarioId of scenarioIds) {
        const found = body.find((s: any) => s.scenario_id === scenarioId)
        expect(found).toBeDefined()
      }
    }
  })

  it('5.1 查看生成任务下的场景列表', async () => {
    expect(generationTaskId).toBeDefined()

    const res = await app.inject({
      method: 'GET',
      url: `${API_PREFIX}/scenario-management/by-generation-task/${generationTaskId}`,
    })

    expect(res.statusCode).toBe(200)
    const body = res.json().data
    expect(Array.isArray(body)).toBe(true)

    if (scenarioIds.length > 0) {
      for (const scenarioId of scenarioIds) {
        const found = body.find((s: any) => s.scenario_id === scenarioId)
        expect(found).toBeDefined()
        expect(found.generation_task_id).toBe(generationTaskId)
      }
    }
  })

  it('6. 新增场景', async () => {
    const newScenario = {
      scenario_id: `e2e_test_scenario_new_${Date.now()}`,
      scenario_name: '新增测试场景',
      description: '这是通过API新增的测试场景',
      tags: ['风量增减调节'],
      // tag_tree_id 为标签树的 Mongo _id（by-tag-tree 查询按 Mongo _id 过滤）
      tag_tree_id: tagTreeMongoId,
      source_query: '新增场景测试',
    }

    const res = await app.inject({
      method: 'POST',
      url: `${API_PREFIX}/scenario-management/`,
      payload: newScenario,
    })

    expect(res.statusCode).toBe(201)
    const body = res.json()
    // reply.success 包裹，statusCode=201
    expect(body.code).toBe(201)
    expect(body.data.scenario_id).toBe(newScenario.scenario_id)

    scenarioIds.push(newScenario.scenario_id)
  })

  it('7. 更新场景信息', async () => {
    const scenarioToUpdate = scenarioIds[0]

    // 先获取场景的MongoDB ID
    const scenario = await scenarioRepository.findByScenarioId(scenarioToUpdate)
    expect(scenario).toBeDefined()

    const res = await app.inject({
      method: 'PUT',
      url: `${API_PREFIX}/scenario-management/${scenario!.id}`,
      payload: {
        scenario_name: '更新后的场景名称',
        description: '这是更新后的描述',
        tags: ['温度直接设定', '显式意图识别'],
      },
    })

    console.log('Update scenario response:', res.statusCode, res.body.substring(0, 200))

    expect(res.statusCode).toBe(200)
    const body = res.json().data
    // reply.success 包裹
    expect(body.scenario_name).toBe('更新后的场景名称')
    expect(body.description).toBe('这是更新后的描述')
    expect(body.tags).toContain('温度直接设定')
  })

  it('8. 删除场景', async () => {
    const scenarioToDelete = scenarioIds[scenarioIds.length - 1]

    // 先获取场景的MongoDB ID
    const scenario = await scenarioRepository.findByScenarioId(scenarioToDelete)
    expect(scenario).toBeDefined()

    const res = await app.inject({
      method: 'DELETE',
      url: `${API_PREFIX}/scenario-management/${scenario!.id}`,
    })

    console.log('Delete scenario response:', res.statusCode, res.body)

    expect(res.statusCode).toBe(200)
    const body = res.json()
    // reply.success 包裹：data=true
    expect(body.code).toBe(200)
    expect(body.data).toBe(true)

    // 验证场景已被删除
    const deletedScenario = await scenarioRepository.findByScenarioId(scenarioToDelete)
    expect(deletedScenario).toBeNull()

    // 从列表中移除
    scenarioIds.pop()
  })

  it('9. 创建数据集', async () => {
    const res = await app.inject({
      method: 'POST',
      url: `${API_PREFIX}/complex_reasoning_dataset/`,
      payload: {
        name: `e2e_test_dataset_${Date.now()}`,
        description: '端到端测试数据集',
      },
    })

    console.log('Create dataset response:', res.statusCode, res.body)

    expect(res.statusCode).toBe(201)
    const body = res.json()
    // dataset.ts 使用 reply.success 包装响应
    expect(body.code).toBe(201)
    expect(body.data.id).toBeDefined()
    expect(body.data.name).toContain('e2e_test_dataset')

    datasetId = body.data.id
  })

  it('10. 为每个场景流式生成用例', async () => {
    // 如果没有生成场景，跳过此测试
    if (scenarioIds.length === 0) {
      console.log('No scenarios generated, skipping case generation test')
      return
    }

    // 场景生成会产出较多场景（阶段1过采样 + 阶段2去重），
    // 用例生成只取前若干个场景验证流式接口可用，避免全量生成耗时过长
    const targetScenarioIds = scenarioIds.slice(0, 3)
    console.log(`Generating cases for ${targetScenarioIds.length}/${scenarioIds.length} scenarios`)

    // 使用流式API实时接收生成的用例
    // 为加快测试，限制迭代参数
    const res = await app.inject({
      method: 'POST',
      url: `${API_PREFIX}/case-generation-stream`,
      payload: {
        scenarioIds: targetScenarioIds,
        datasetId: datasetId,
        casesPerScenario: 1, // 每个场景生成1个用例以加快测试
        tagTreeName: tagTreeName,
        // 测试配置：限制迭代以加快测试速度
        maxIterations: 2,
        maxRefineRoundsPerBatch: 1,
        auditConcurrency: 2,
        fixConcurrency: 2,
      },
    })

    console.log('Case generation stream response status:', res.statusCode)

    expect(res.statusCode).toBe(200)
    expect(res.headers['content-type']).toContain('text/event-stream')

    // 解析SSE响应
    const events = parseSSE(res.body)

    // 收集用例事件
    const cases: any[] = []
    const progressEvents: any[] = []
    let completeEvent: any = null
    let errorEvent: any = null

    for (const event of events) {
      if (event.type === 'case') {
        cases.push(event.data.caseItem)
        console.log(`Received case via stream: ${event.data.caseItem.case_id} (scenario: ${event.data.scenarioName})`)
      } else if (event.type === 'progress') {
        progressEvents.push(event.data)
        console.log(`Progress: ${event.data.stage} ${event.data.current}/${event.data.total}`)
      } else if (event.type === 'complete') {
        completeEvent = event.data
        console.log(`Stream complete: ${event.data.totalGenerated} cases generated`)
      } else if (event.type === 'error') {
        errorEvent = event.data
        console.error(`Stream error: ${event.data.message}`)
      }
    }

    // 验证没有错误
    expect(errorEvent).toBeNull()

    console.log(`Total cases received via stream: ${cases.length}`)

    // 验证生成的用例都有必要的字段
    for (const testCase of cases) {
      expect(testCase.case_id).toBeDefined()
      expect(testCase.dataset_id).toBe(datasetId)
      expect(testCase.source_scenario_id).toBeDefined()
    }

    // 验证完成事件
    expect(completeEvent).toBeDefined()
    expect(completeEvent.totalGenerated).toBeGreaterThanOrEqual(0)
    expect(completeEvent.totalScenarios).toBe(targetScenarioIds.length)
  }, 600000) // 10分钟超时，因为需要调用LLM进行生成、审核、修复

  it('11. 查看数据集下的用例并验证', async () => {
    const res = await app.inject({
      method: 'GET',
      url: `${API_PREFIX}/complex_reasoning_case/list?dataset_id=${datasetId}`,
    })

    console.log('List dataset items response:', res.statusCode, res.body.substring(0, 200))

    expect(res.statusCode).toBe(200)
    const body = res.json()
    expect(body.code).toBe(200)
    expect(Array.isArray(body.data)).toBe(true)

    // 实际用例数量取决于LLM生成和审核结果
    console.log(`Found ${body.data.length} cases in dataset (generated by LLM)`)

    // 如果有用例，验证字段结构
    for (const testCase of body.data) {
      expect(testCase.case_id).toBeDefined()
      expect(String(testCase.dataset_id)).toBe(datasetId)
      expect(testCase.user_query_lists).toBeDefined()
      expect(Array.isArray(testCase.user_query_lists)).toBe(true)
      expect(testCase.expected_script).toBeDefined()
      expect(testCase.nl_assertion).toBeDefined()
      expect(Array.isArray(testCase.nl_assertion)).toBe(true)
    }
  })

  it('12. 查看场景下的用例列表', async () => {
    // 如果没有生成场景，跳过此测试
    if (scenarioIds.length === 0) {
      console.log('No scenarios generated, skipping scenario cases test')
      return
    }

    // 测试场景管理中的查询场景下用例接口
    const scenarioId = scenarioIds[0]

    const res = await app.inject({
      method: 'GET',
      url: `${API_PREFIX}/scenario-management/${encodeURIComponent(scenarioId)}/cases`,
    })

    console.log('Scenario cases response:', res.statusCode, res.body.substring(0, 200))

    expect(res.statusCode).toBe(200)
    const body = res.json()
    // reply.success 包裹：data 为数组
    expect(body.code).toBe(200)
    expect(Array.isArray(body.data)).toBe(true)
  })
})
