// 树形结构转列表
export function treeToList<T extends { children?: T[] }>(tree: T[]): T[] {
  const list: T[] = []

  const traverse = (nodes: T[]) => {
    nodes.forEach((node) => {
      list.push({ ...node, children: undefined })
      if (node.children && node.children.length > 0) {
        traverse(node.children)
      }
    })
  }

  traverse(tree)
  return list
}

// 列表转树形结构
export function listToTree<T extends { id?: string; parent_id?: string; children?: T[] }>(list: T[]): T[] {
  const map: Record<string, T> = {}
  const tree: T[] = []

  list.forEach((item) => {
    if (item.id) map[item.id] = { ...item }
  })

  list.forEach((item) => {
    if (item.id) {
      const node = map[item.id]
      if (item.parent_id && map[item.parent_id]) {
        if (!map[item.parent_id].children) map[item.parent_id].children = []

        map[item.parent_id].children!.push(node)
      } else {
        tree.push(node)
      }
    }
  })

  return tree
}
