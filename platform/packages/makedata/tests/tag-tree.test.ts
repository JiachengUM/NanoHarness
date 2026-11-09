import { describe, it, expect, beforeEach } from 'vitest'
import { TagTree, previewTagTree } from '../src/core/tag-tree'
import { loadTestTagTree } from './test-utils'

describe('TagTree', () => {
  let testTree: TagTree

  beforeEach(() => {
    // 每个测试使用真实的 vehicle-tag-tree.json
    testTree = loadTestTagTree()
  })

  describe('fromJSON', () => {
    it('should create TagTree from vehicle-tag-tree.json', () => {
      expect(testTree).toBeDefined()
      expect(testTree.root).toBeDefined()
      expect(testTree.root.name).toBe('车机助手评测标签树')
      expect(testTree.taggingGuideline).toContain('叶子标签')
    })

    it('should throw error for invalid JSON', () => {
      expect(() => {
        TagTree.fromJSON({ invalid: 'data' } as any)
      }).toThrow('root')
    })

    it('should detect duplicate node names', () => {
      const duplicateTree = {
        root: {
          name: '重复测试',
          description: '测试',
          children: [
            { name: '重复名称', description: '节点1', children: [] },
            { name: '重复名称', description: '节点2', children: [] },
          ],
        },
        tagging_guideline: '测试',
      }

      expect(() => TagTree.fromJSON(duplicateTree)).toThrow('重名')
    })
  })

  describe('getLeafTagNames', () => {
    it('should return all leaf tag names from vehicle tree', () => {
      const leaves = testTree.getLeafTagNames()
      
      expect(leaves.length).toBeGreaterThan(50) // vehicle tree 有大量叶子标签
      expect(leaves).toContain('温度增减调节')
      expect(leaves).toContain('精确地点直达')
      expect(leaves).toContain('按歌手点播')
      expect(leaves).toContain('多轮对话_2到3轮')
    })

    it('should not include intermediate nodes', () => {
      const leaves = testTree.getLeafTagNames()
      
      expect(leaves).not.toContain('空调操作')  // 中间节点
      expect(leaves).not.toContain('车控操作')  // 中间节点
      expect(leaves).not.toContain('产品视角标签子树')  // 根节点
    })

    it('should return only leaf nodes', () => {
      const leaves = testTree.getLeafTagNames()
      const allNodes = testTree.root.iterNodes()
      
      // 所有叶子标签应该是所有节点的一个子集
      expect(leaves.length).toBeLessThan(allNodes.length)
    })
  })

  describe('isLeaf', () => {
    it('should identify leaf nodes correctly', () => {
      // 获取一个叶子节点
      const leafNode = testTree.root.iterLeafNodes()[0]
      expect(leafNode.isLeaf).toBe(true)
    })

    it('should identify non-leaf nodes correctly', () => {
      // 根节点肯定不是叶子
      expect(testTree.root.isLeaf).toBe(false)
    })
  })

  describe('iterNodes', () => {
    it('should iterate all nodes in vehicle tree', () => {
      const nodes = testTree.root.iterNodes()
      
      expect(nodes.length).toBeGreaterThan(100) // vehicle tree 有很多节点
      
      // 验证包含关键节点
      const nodeNames = nodes.map(n => n.name)
      expect(nodeNames).toContain('车机助手评测标签树')
      expect(nodeNames).toContain('温度增减调节')
      expect(nodeNames).toContain('精确地点直达')
    })

    it('should include root node', () => {
      const nodes = testTree.root.iterNodes()
      expect(nodes[0].name).toBe('车机助手评测标签树')
    })
  })

  describe('iterLeafNodes', () => {
    it('should iterate only leaf nodes', () => {
      const leafNodes = testTree.root.iterLeafNodes()
      const leafNames = leafNodes.map(n => n.name)
      
      // 所有返回的节点都应该是叶子
      leafNodes.forEach(node => {
        expect(node.isLeaf).toBe(true)
      })

      // 验证包含已知的叶子节点
      expect(leafNames).toContain('温度增减调节')
      expect(leafNames).toContain('常用地点记忆')
    })
  })

  describe('getNodeByName', () => {
    it('should find existing node by name', () => {
      const node = testTree.getNodeByName('温度增减调节')
      expect(node).toBeDefined()
      expect(node.name).toBe('温度增减调节')
      expect(node.isLeaf).toBe(true)
    })

    it('should find intermediate node by name', () => {
      const node = testTree.getNodeByName('空调操作')
      expect(node).toBeDefined()
      expect(node.isLeaf).toBe(false)
    })

    it('should throw error for non-existent node', () => {
      expect(() => {
        testTree.getNodeByName('不存在的节点名称')
      }).toThrow('节点不存在')
    })
  })

  describe('validateCaseTags', () => {
    it('should pass for valid leaf tags', () => {
      const validTags = ['温度增减调节', '精确地点直达', '按歌手点播']
      expect(() => testTree.validateCaseTags(validTags)).not.toThrow()
    })

    it('should throw for intermediate node tags', () => {
      const invalidTags = ['空调操作']
      expect(() => testTree.validateCaseTags(invalidTags)).toThrow('不是叶子节点')
    })

    it('should throw for non-existent tags', () => {
      const invalidTags = ['不存在的标签']
      expect(() => testTree.validateCaseTags(invalidTags)).toThrow()
    })
  })

  describe('toPrettyString', () => {
    it('should generate tree visualization', () => {
      const pretty = testTree.toPrettyString(true)
      
      expect(pretty).toContain('车机助手评测标签树')
      expect(pretty).toContain('温度增减调节 [leaf]')
      expect(pretty).toContain('├─') // 树形连接符
      expect(pretty).toContain('└─') // 树形连接符
    })

    it('should generate without leaf marks when configured', () => {
      const pretty = testTree.toPrettyString(false)
      
      expect(pretty).not.toContain('[leaf]')
    })
  })

  describe('previewTagTree', () => {
    it('should generate preview with tree and leaf list', () => {
      const preview = previewTagTree(testTree, {
        showTree: true,
        showLeafList: true,
        title: '完整预览',
      })

      expect(preview).toContain('完整预览')
      expect(preview).toContain('车机助手评测标签树')
      expect(preview).toContain('叶子标签总数')
    })

    it('should generate preview with only leaf list', () => {
      const preview = previewTagTree(testTree, {
        showTree: false,
        showLeafList: true,
        title: 'Leaf List Only',
      })

      // 不包含树形结构符号
      expect(preview).not.toContain('├─')
      // 应该包含叶子标签
      expect(preview).toContain('温度增减调节')
    })

    it('should generate preview with only tree structure', () => {
      const preview = previewTagTree(testTree, {
        showTree: true,
        showLeafList: false,
        title: '仅树形',
      })

      expect(preview).toContain('仅树形')
      expect(preview).toContain('├─')
      expect(preview).not.toContain('叶子标签总数')
    })
  })

  describe('toData and toJSON', () => {
    it('should convert to data object', () => {
      const data = testTree.toData()
      
      expect(data.root.name).toBe('车机助手评测标签树')
      expect(data.tagging_guideline).toBeDefined()
    })

    it('should convert to JSON string', () => {
      const json = testTree.toJSON()
      const parsed = JSON.parse(json)
      
      expect(parsed.root.name).toBe('车机助手评测标签树')
    })

    it('should round-trip correctly', () => {
      const json = testTree.toJSON()
      const newTree = TagTree.fromJSON(json)
      
      expect(newTree.root.name).toBe(testTree.root.name)
      expect(newTree.getLeafTagNames()).toEqual(testTree.getLeafTagNames())
    })
  })

  describe('Real vehicle tree validation', () => {
    it('should have expected top-level categories from real JSON', () => {
      const rootChildren = testTree.root.children.map(c => c.name)
      
      // 验证实际存在于 JSON 中的顶级分类
      expect(rootChildren).toContain('产品视角标签子树')
      expect(rootChildren.length).toBeGreaterThanOrEqual(1)
    })

    it('should have car control related tags', () => {
      const leaves = testTree.getLeafTagNames()
      
      // 空调相关叶子标签
      expect(leaves).toContain('温度增减调节')
      expect(leaves).toContain('温度直接设定')
      expect(leaves).toContain('风量增减调节')
      expect(leaves).toContain('空调开关')
    })

    it('should have navigation-related tags', () => {
      const leaves = testTree.getLeafTagNames()
      
      // 导航相关 - 使用实际存在于 JSON 中的名称
      expect(leaves).toContain('精确地点直达')
      expect(leaves.some(l => l.includes('导航'))).toBe(true)
    })

    it('should have a large number of leaf tags', () => {
      const leaves = testTree.getLeafTagNames()
      
      // vehicle tree 应该有很多叶子标签
      expect(leaves.length).toBeGreaterThan(50)
    })
  })
})
