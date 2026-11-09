import { lazy } from 'react'

const icons = {
  logo: lazy(() => import('@/assets/icons/logo.svg?react')),
}

export type IconName = keyof typeof icons

export const getIcon = (name: IconName) => {
  return icons[name]
}
