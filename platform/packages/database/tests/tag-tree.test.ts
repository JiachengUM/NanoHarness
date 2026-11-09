import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'
import { connect, disconnect, tagTreeRepository } from '../src'

const MONGO_URI = 'mongodb://127.0.0.1:27017/eval_platform'
const TEST_TREE_NAME_PREFIX = '__test_tag_tree__'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

// 加载示例车辆标签树
function loadVehicleTagTree(): any {
  const treePath = join(__dirname, '../../makedata/examples/data/vehicle-tag-tree.json')
  return JSON.parse(readFileSync(treePath, 'utf-8'))
}

// 从树中提取所有叶子标签名
function extractLeafTags(node: any): string[] {
  const leaves: string[] = []
  if (!node.children || node.children.length === 0) {
    leaves.push(node.name)
  } else {
    for (const child of node.children) {
      leaves.push(...extractLeafTags(child))
    }
  }
  return leaves
}

function makeTreeData(name: string, overrides: Record<string, unknown> = {}) {
  return {
    name: `${TEST_TREE_NAME_PREFIX}_${name}_${Date.now()}`,
    description: 'Test tag tree for database test',
    tree: loadVehicleTagTree(),
    ...overrides,
  }
}

describe('TagTree CRUD', () => {
  const createdTreeIds: string[] = []

  beforeAll(async () => {
    await connect(MONGO_URI)

    // 清理之前测试残留的数据
    const existingTrees = await tagTreeRepository.listTagTrees()
    for (const tree of existingTrees) {
      if (tree.name.startsWith(TEST_TREE_NAME_PREFIX)) {
        await tagTreeRepository.deleteTagTree(tree.id)
      }
    }
  })

  afterAll(async () => {
    // 清理测试数据
    for (const id of createdTreeIds) {
      await tagTreeRepository.deleteTagTree(id)
    }
    await disconnect()
  })

  it('should create a tag tree with vehicle data', async () => {
    const dto = makeTreeData('create')
    const created = await tagTreeRepository.createTagTree(dto)

    expect(created).toBeDefined()
    expect(created.id).toBeDefined()
    expect(created.name).toBe(dto.name)
    expect(created.description).toBe(dto.description)
    expect(created.tree).toBeDefined()
    // 验证使用的是 vehicle-tag-tree.json 数据
    expect(created.tree.root.name).toBe('车机助手评测标签树')
    expect(created.tree.root.children.length).toBeGreaterThan(0)

    createdTreeIds.push(created.id)
  })

  it('should find a tag tree by name', async () => {
    const dto = makeTreeData('find_by_name')
    const created = await tagTreeRepository.createTagTree(dto)
    createdTreeIds.push(created.id)

    const found = await tagTreeRepository.findByName(dto.name)

    expect(found).toBeDefined()
    expect(found?.name).toBe(dto.name)
    expect(found?.tree.root.name).toBe('车机助手评测标签树')
  })

  it('should return null when tag tree not found', async () => {
    const found = await tagTreeRepository.findByName('non_existent_tree')
    expect(found).toBeNull()
  })

  it('should list all tag trees', async () => {
    const initialList = await tagTreeRepository.listTagTrees()
    const initialCount = initialList.filter((t) => t.name.startsWith(TEST_TREE_NAME_PREFIX)).length

    const dto1 = makeTreeData('list_1')
    const dto2 = makeTreeData('list_2')
    const created1 = await tagTreeRepository.createTagTree(dto1)
    const created2 = await tagTreeRepository.createTagTree(dto2)
    createdTreeIds.push(created1.id, created2.id)

    const list = await tagTreeRepository.listTagTrees()
    const testTrees = list.filter((t) => t.name.startsWith(TEST_TREE_NAME_PREFIX))

    expect(testTrees.length).toBeGreaterThanOrEqual(initialCount + 2)
  })

  it('should update tag tree metadata', async () => {
    const dto = makeTreeData('update')
    const created = await tagTreeRepository.createTagTree(dto)
    createdTreeIds.push(created.id)

    const updated = await tagTreeRepository.updateTagTree(created.id, {
      description: 'Updated description',
    })

    expect(updated).toBeDefined()
    expect(updated?.description).toBe('Updated description')
    // tree 结构不应该改变
    expect(updated?.tree.root.name).toBe('车机助手评测标签树')
  })

  it('should delete a tag tree', async () => {
    const dto = makeTreeData('delete')
    const created = await tagTreeRepository.createTagTree(dto)
    const id = created.id

    const deleted = await tagTreeRepository.deleteTagTree(id)
    expect(deleted).toBe(true)

    const found = await tagTreeRepository.findByName(dto.name)
    expect(found).toBeNull()
  })

  it('should verify leaf tags from vehicle tree', async () => {
    const dto = makeTreeData('leaf_tags')
    const created = await tagTreeRepository.createTagTree(dto)
    createdTreeIds.push(created.id)

    // 验证树结构
    const leafTags = extractLeafTags(created.tree.root)

    // 验证 vehicle-tag-tree.json 中的典型叶子标签存在
    expect(leafTags).toContain('温度增减调节')
    expect(leafTags).toContain('温度直接设定')
    expect(leafTags).toContain('风量增减调节')
    expect(leafTags).toContain('精确地点直达')
    expect(leafTags).toContain('模糊地点表达理解')
    expect(leafTags.length).toBeGreaterThan(100)

    // 验证不是叶子节点的标签不在列表中
    expect(leafTags).not.toContain('车机助手评测标签树')
    expect(leafTags).not.toContain('车控操作')
    expect(leafTags).not.toContain('温度调节')
  })
})
