import React, { useEffect, useMemo, useState } from 'react'
import { TreeSelect } from 'antd'
import type { GetProp, TreeSelectProps } from 'antd'

type TreeDataType = GetProp<TreeSelectProps, 'treeData'>

type Props = TreeSelectProps & {
  onlyLeaf?: boolean
  value?: React.Key
  onChange?: (value: React.Key) => void
  treeData?: TreeDataType
}

const App: React.FC<Props> = ({ value, onChange, treeData, onlyLeaf, ...otherProps }) => {
  const [treeValue, setTreeValue] = useState<React.Key>()

  const currentTreeData = useMemo(() => {
    if (!onlyLeaf) return treeData

    const loop = (data: TreeDataType): TreeDataType => {
      return data.map((item) => {
        return {
          ...item,
          children: loop(item.children || []),
          selectable: item.children?.length ? false : true,
        }
      })
    }

    return loop(treeData || [])
  }, [treeData, onlyLeaf])

  const handleChange = (e: React.Key) => {
    setTreeValue(e)

    onChange?.(e)
  }

  useEffect(() => {
    if (!value) setTreeValue('')

    if (value) setTreeValue(value as React.Key)
  }, [value])

  return (
    <>
      <TreeSelect
        value={treeValue}
        onSelect={(e) => handleChange(e as React.Key)}
        treeData={currentTreeData}
        {...otherProps}
      ></TreeSelect>
    </>
  )
}

export default App
