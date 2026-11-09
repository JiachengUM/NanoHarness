import React from 'react'
import Icon from '@ant-design/icons'
import { getIcon } from './icons'
import type { IconName } from './icons'
import type { GetProps } from 'antd'

type Props = {
  name: IconName
} & GetProps<typeof Icon>

const SvgIcon: React.FC<Props> = ({ name, ...iconProps }) => {
  const IconComponent = getIcon(name)

  return <Icon component={IconComponent} {...iconProps} />
}

export default SvgIcon
