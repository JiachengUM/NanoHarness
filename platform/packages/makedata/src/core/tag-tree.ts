/**
 * Tag Tree - TypeScript 版本的标签树实现
 * 对应老项目中的 tag_tree_schema.py
 */

export interface TagTreeNodeData {
  name: string
  description?: string
  children?: TagTreeNodeData[]
}

export interface TagTreeData {
  root: TagTreeNodeData
  tagging_guideline?: string
}

export class TagTreeNode {
  name: string
  description: string
  children: TagTreeNode[]

  constructor(data: TagTreeNodeData) {
    this.name = data.name
    this.description = data.description || ''
    this.children = (data.children || []).map(child => new TagTreeNode(child))
  }

  /**
   * 判断当前节点是否为叶子节点
   */
  get isLeaf(): boolean {
    return this.children.length === 0
  }

  /**
   * 深度优先遍历当前节点及其全部后代节点
   */
  iterNodes(): TagTreeNode[] {
    const nodes: TagTreeNode[] = [this]
    for (const child of this.children) {
      nodes.push(...child.iterNodes())
    }
    return nodes
  }

  /**
   * 深度优先收集当前节点子树中的所有叶子节点
   */
  iterLeafNodes(): TagTreeNode[] {
    if (this.isLeaf) {
      return [this]
    }
    const leaves: TagTreeNode[] = []
    for (const child of this.children) {
      leaves.push(...child.iterLeafNodes())
    }
    return leaves
  }

  /**
   * 转换为原始数据对象
   */
  toData(): TagTreeNodeData {
    const data: TagTreeNodeData = {
      name: this.name,
      description: this.description,
    }
    if (this.children.length > 0) {
      data.children = this.children.map(child => child.toData())
    }
    return data
  }
}

export class TagTree {
  root: TagTreeNode
  taggingGuideline: string

  constructor(data: TagTreeData) {
    this.root = new TagTreeNode(data.root)
    this.taggingGuideline = data.tagging_guideline || 
      '请基于case目标与通过标准，从叶子标签中选择最有证据支持的标签。'
  }

  /**
   * 从 JSON 字符串或对象构建标签树
   */
  static fromJSON(jsonData: string | TagTreeData): TagTree {
    const data = typeof jsonData === 'string' ? JSON.parse(jsonData) as TagTreeData : jsonData
    
    if (!data || typeof data !== 'object') {
      throw new Error('jsonData 必须是 JSON object（对象）')
    }
    if (!data.root) {
      throw new Error('jsonData 最外层必须且只能提供一个 root 字段')
    }
    
    const tree = new TagTree(data)
    tree._ensureUniqueNodeNames()
    return tree
  }

  /**
   * 返回可用于 case.tags 的所有叶子标签名
   */
  getLeafTagNames(): string[] {
    return this.root.iterLeafNodes().map(node => node.name)
  }

  /**
   * 按节点名称精确查找节点
   */
  getNodeByName(nodeName: string): TagTreeNode {
    for (const node of this.root.iterNodes()) {
      if (node.name === nodeName) {
        return node
      }
    }
    throw new Error(`节点不存在: ${nodeName}`)
  }

  /**
   * 校验一个 case 的 tags 是否全部是叶子标签
   */
  validateCaseTags(tags: string[]): void {
    const leafNames = new Set(this.getLeafTagNames())
    const invalidTags = [...new Set(tags)].filter(tag => !leafNames.has(tag))
    
    if (invalidTags.length > 0) {
      throw new Error(
        `以下标签不是叶子节点标签，不能用于case打标: ${invalidTags.join(', ')}`
      )
    }
  }

  /**
   * 将标签树转为便于阅读的树形字符串
   * 
   * Example:
   * 根
   * ├── 一级A
   * │   ├── 叶子A1 [leaf]
   * │   └── 叶子A2 [leaf]
   * └── 一级B [leaf]
   */
  toPrettyString(showLeafMark: boolean = true): string {
    return this._formatSubtree(
      this.root,
      '',
      true,
      showLeafMark,
      true
    )
  }

  private _formatSubtree(
    node: TagTreeNode,
    prefix: string,
    isLast: boolean,
    showLeafMark: boolean,
    isRoot: boolean = false
  ): string {
    let nodeLabel = node.name
    if (showLeafMark && node.isLeaf) {
      nodeLabel = `${nodeLabel} [leaf]`
    }

    // 根节点不显示连接符，子节点按是否末尾选择不同连接符
    let currentLine: string
    if (isRoot) {
      currentLine = nodeLabel
    } else {
      const connector = isLast ? '└── ' : '├── '
      currentLine = `${prefix}${connector}${nodeLabel}`
    }

    if (node.children.length === 0) {
      return currentLine
    }

    const childPrefix = prefix + (isLast || isRoot ? '    ' : '│   ')
    const childLines: string[] = []
    
    for (let index = 0; index < node.children.length; index++) {
      const child = node.children[index]
      const childIsLast = index === node.children.length - 1
      childLines.push(
        this._formatSubtree(
          child,
          childPrefix,
          childIsLast,
          showLeafMark,
          false
        )
      )
    }
    
    return currentLine + '\n' + childLines.join('\n')
  }

  /**
   * 内部唯一性检查：全树任何层级都不允许重名
   */
  private _ensureUniqueNodeNames(): void {
    const allNames = this.root.iterNodes().map(node => node.name)
    const duplicateNames = [...new Set(
      allNames.filter((name, index) => allNames.indexOf(name) !== index)
    )]
    
    if (duplicateNames.length > 0) {
      throw new Error(
        `标签树中存在重名节点，不允许重复: ${duplicateNames.join(', ')}`
      )
    }
  }

  /**
   * 转换为 JSON 数据对象
   */
  toData(): TagTreeData {
    return {
      root: this.root.toData(),
      tagging_guideline: this.taggingGuideline,
    }
  }

  /**
   * 转换为 JSON 字符串
   */
  toJSON(indent: number = 2): string {
    return JSON.stringify(this.toData(), null, indent)
  }
}

/**
 * 打印标签树的可视化字符串（类似老项目的 preview_vehicle_tag_tree.py）
 */
export function previewTagTree(
  tree: TagTree,
  options?: {
    showTree?: boolean
    showLeafList?: boolean
    title?: string
  }
): string {
  const { 
    showTree = true, 
    showLeafList = false,
    title = '标签树预览'
  } = options || {}
  
  const lines: string[] = []
  
  if (showTree) {
    lines.push(`=== ${title}（树形）===`)
    lines.push(tree.toPrettyString(true))
    lines.push('')
  }
  
  if (showLeafList) {
    const leafTags = tree.getLeafTagNames()
    lines.push(`=== 叶子标签总数: ${leafTags.length} ===`)
    leafTags.forEach((tag, index) => {
      lines.push(`${(index + 1).toString().padStart(2, '0')}. ${tag}`)
    })
  }
  
  return lines.join('\n')
}
