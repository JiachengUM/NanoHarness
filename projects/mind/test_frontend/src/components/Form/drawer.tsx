import React, { useMemo } from 'react'
import { Button, Drawer, Space } from 'antd'
import type { GetProps } from 'antd'

type DrawerProps = GetProps<typeof Drawer>

type ExDrawerProps = DrawerProps & {
  title: string
  open: boolean
  setOpen: (open: boolean) => void
  onSave?: () => void
  children?: React.ReactNode
  fullScreen?: boolean
  maskClosable?: boolean
  destroyOnHidden?: boolean
  width?: number | string
  extra?: React.ReactNode
}

const ExDrawer = (props: ExDrawerProps) => {
  const {
    open,
    setOpen,
    title,
    fullScreen,
    onSave,
    children,
    width,
    destroyOnHidden = true,
    maskClosable = false,
    styles,
  } = props

  const drawerWidth = useMemo(() => {
    if (fullScreen) return '100%'
    if (width) return width
    return 720
  }, [fullScreen, width])

  return (
    <Drawer
      title={title}
      width={drawerWidth}
      placement="right"
      open={open}
      maskClosable={maskClosable}
      destroyOnHidden={destroyOnHidden}
      onClose={() => setOpen(false)}
      styles={{
        header: { padding: '14px' },
        body: { padding: 16 },
        ...styles,
      }}
      extra={
        props.extra || (
          <>
            <Space size="middle">
              {onSave && (
                <>
                  <Button onClick={() => setOpen(false)}>取消</Button>
                  <Button type="primary" onClick={() => onSave()}>
                    保存
                  </Button>
                </>
              )}
            </Space>
          </>
        )
      }
    >
      {children}
    </Drawer>
  )
}

export default ExDrawer
