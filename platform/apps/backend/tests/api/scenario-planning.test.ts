/**
 * Scenario Planning API 测试
 */

import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest'
import type { FastifyInstance } from 'fastify'
import { buildApp } from '../../src/core/app'
import { API_PREFIX } from '../../src/constants'
import {
  connect,
  disconnect,
  tagTreeRepository,
  scenarioPlanRepository,
  generationTaskRepository,
} from '@eval-platform/database'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const MONGO_URI = 'mongodb://127.0.0.1:27017/eval_platform_planning_test'

describe('Scenario Planning API', () => {
  let app: FastifyInstance
  let tagTreeName: string

  beforeAll(async () => {
    // 连接数据库
    await connect(MONGO_URI)

    // 清理测试数据
    await cleanupTestData()

    // 构建应用
    app = await buildApp({ logger: false })

    // 上传测试标签树
    await uploadTestTagTree()
  }, 60000)

  afterAll(async () => {
    await app.close()
    await cleanupTestData()
    await disconnect()
  }, 30000)

  beforeEach(async () => {
    // 每次测试前清理 plan 数据
    const plans = await scenarioPlanRepository.listPlans()
    for (const plan of plans) {
      await scenarioPlanRepository.deletePlan(plan.id)
    }

    const tasks = await generationTaskRepository.listGenerationTasks()
    for (const task of tasks) {
      if (task.name.startsWith('planning_test_task_')) await generationTaskRepository.deleteGenerationTask(task.id)
    }
  })

  async function cleanupTestData() {
    const trees = await tagTreeRepository.listTagTrees()
    for (const tree of trees) {
      if (tree.name.startsWith('planning_test_')) {
        await tagTreeRepository.deleteTagTree(tree.id)
      }
    }
  }

  async function uploadTestTagTree() {
    const treePath = join(__dirname, '../../../../packages/makedata/examples/data/vehicle-tag-tree.json')
    const treeData = JSON.parse(readFileSync(treePath, 'utf-8'))
    tagTreeName = `planning_test_tree_${Date.now()}`

    const res = await app.inject({
      method: 'POST',
      url: `${API_PREFIX}/tag-tree`,
      payload: {
        name: tagTreeName,
        description: 'Planning API 测试用标签树',
        tree: treeData,
      },
    })

    expect(res.statusCode).toBe(201)  // 创建成功返回 201
    console.log('Test tag tree uploaded:', tagTreeName)
  }

  async function createTestTaskId() {
    const task = await generationTaskRepository.createGenerationTask({
      name: `planning_test_task_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`,
      description: 'Scenario Planning API 测试任务',
      creator: 'test',
    })
    return task.id
  }

  describe('POST /api/scenario-planning/generate', () => {
    it('should generate a scenario plan', async () => {
      const query = '生成空调温度调节场景'
      const taskId = await createTestTaskId()

      const res = await app.inject({
        method: 'POST',
        url: `${API_PREFIX}/scenario-planning/generate`,
        payload: {
          query,
          tag_tree_name: tagTreeName,
          task_id: taskId,
        },
      })

      expect(res.statusCode).toBe(200)
      const body = res.json()
      const plan = body.data

      expect(plan.id).toBeDefined()
      expect(plan.original_query).toBe(query)
      expect(plan.task_description).toBeDefined()
      expect(plan.target_tags).toBeDefined()
      expect(plan.target_tags.length).toBeGreaterThan(0)
      expect((plan as any).scenario_patterns).toBeUndefined()
      expect(plan.interpretation_notes).toBeDefined()
      expect(plan.status).toBe('pending')
      expect(plan.tag_tree_name).toBe(tagTreeName)

      console.log('Plan created:', {
        id: plan.id,
        target_tags_count: plan.target_tags.length,
      })
    }, 120000)

    it('should return 404 for non-existent tag tree', async () => {
      // 这个测试不需要 LLM
      const res = await app.inject({
        method: 'POST',
        url: `${API_PREFIX}/scenario-planning/generate`,
        payload: {
          query: '生成场景',
          tag_tree_name: 'non-existent-tree',
          task_id: await createTestTaskId(),
        },
      })

      expect(res.statusCode).toBe(404)
      expect(res.json().message).toContain('标签树不存在')
    })

    it('should require all required fields', async () => {
      // Missing query
      let res = await app.inject({
        method: 'POST',
        url: `${API_PREFIX}/scenario-planning/generate`,
        payload: {
          tag_tree_name: tagTreeName,
          task_id: await createTestTaskId(),
        },
      })
      expect(res.statusCode).toBe(400)

      // Missing task_id
      res = await app.inject({
        method: 'POST',
        url: `${API_PREFIX}/scenario-planning/generate`,
        payload: {
          query: '生成场景',
          tag_tree_name: tagTreeName,
        },
      })
      expect(res.statusCode).toBe(400)
    })
  })

  describe('GET /api/scenario-planning/:id', () => {
    it('should get a plan by id', async () => {
      // 先创建一个 plan
      const createRes = await app.inject({
        method: 'POST',
        url: `${API_PREFIX}/scenario-planning/generate`,
        payload: {
          query: '生成导航场景',
          tag_tree_name: tagTreeName,
          task_id: await createTestTaskId(),
        },
      })
      expect(createRes.statusCode).toBe(200)
      const planId = createRes.json().data.id

      // 获取 plan
      const res = await app.inject({
        method: 'GET',
        url: `${API_PREFIX}/scenario-planning/${planId}`,
      })

      expect(res.statusCode).toBe(200)
      const body = res.json()

      expect(body.data.id).toBe(planId)
      expect(body.data.task_description).toBeDefined()
      expect(body.data.target_tags).toBeDefined()
    }, 120000)

    it('should return 404 for non-existent plan', async () => {
      const res = await app.inject({
        method: 'GET',
        url: `${API_PREFIX}/scenario-planning/non-existent-plan-id`,
      })

      expect(res.statusCode).toBe(404)
    })
  })

  describe('PUT /api/scenario-planning/:id', () => {
    it('should update plan status to confirmed', async () => {
      // 先创建一个 plan
      const createRes = await app.inject({
        method: 'POST',
        url: `${API_PREFIX}/scenario-planning/generate`,
        payload: {
          query: '生成音乐播放场景',
          tag_tree_name: tagTreeName,
          task_id: await createTestTaskId(),
        },
      })
      expect(createRes.statusCode).toBe(200)
      const planId = createRes.json().data.id

      // 确认 plan
      const res = await app.inject({
        method: 'PUT',
        url: `${API_PREFIX}/scenario-planning/${planId}`,
        payload: {
          status: 'confirmed',
        },
      })

      expect(res.statusCode).toBe(200)
      expect(res.json().data.status).toBe('confirmed')
    }, 120000)

    it('should update plan status to cancelled', async () => {
      // 先创建一个 plan
      const createRes = await app.inject({
        method: 'POST',
        url: `${API_PREFIX}/scenario-planning/generate`,
        payload: {
          query: '生成场景',
          tag_tree_name: tagTreeName,
          task_id: await createTestTaskId(),
        },
      })
      expect(createRes.statusCode).toBe(200)
      const planId = createRes.json().data.id

      // 取消 plan
      const res = await app.inject({
        method: 'PUT',
        url: `${API_PREFIX}/scenario-planning/${planId}`,
        payload: {
          status: 'cancelled',
        },
      })

      expect(res.statusCode).toBe(200)
      expect(res.json().data.status).toBe('cancelled')
    }, 120000)
  })

  describe('GET /api/scenario-planning/list?task_id=', () => {
    it('should list plans by task id', async () => {
      const taskId = await createTestTaskId()

      // 创建多个 plans
      for (let i = 0; i < 2; i++) {
        const res = await app.inject({
          method: 'POST',
          url: `${API_PREFIX}/scenario-planning/generate`,
          payload: {
            query: `生成场景 ${i}`,
            tag_tree_name: tagTreeName,
            task_id: taskId,
          },
        })
        expect(res.statusCode).toBe(200)
      }

      // 获取列表
      const res = await app.inject({
        method: 'GET',
        url: `${API_PREFIX}/scenario-planning/list?task_id=${taskId}`,
      })

      expect(res.statusCode).toBe(200)
      const body = res.json()

      expect(body.data).toBeDefined()
      expect(Array.isArray(body.data)).toBe(true)
      expect(body.data.length).toBe(2)

      for (const plan of body.data) {
        expect(plan.id).toBeDefined()
        expect(plan.task_id).toBe(taskId)
        expect(plan.original_query).toBeDefined()
        expect(plan.target_tags).toBeDefined()
        expect(plan.status).toBeDefined()
      }
    }, 300000)
  })
})
