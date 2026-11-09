type TagTreeNodeData = {
  name: string
  children?: TagTreeNodeData[]
}

type TagTreeData = {
  root?: TagTreeNodeData
}

const collectLeafTagNames = (node: TagTreeNodeData): string[] => {
  if (!node.children?.length) return [node.name]
  return node.children.flatMap(collectLeafTagNames)
}

export const getLeafTagNamesFromTree = (tree: object): string[] => {
  const data = tree as TagTreeData
  if (!data?.root) return []
  return collectLeafTagNames(data.root)
}
